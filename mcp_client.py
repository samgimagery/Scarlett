"""
MCP Client — communicates with Smart Connections MCP server via subprocess + JSON-RPC.

Uses line-by-line reading to properly handle the init → tool call sequence.
"""
import json
import subprocess
import time
import os
import re
import unicodedata
from pathlib import Path
from config import MCP_SERVER_PATH, VAULT_PATH, SIMILARITY_THRESHOLD, MAX_CONTEXT_NOTES


def _run_mcp_tool(tool_name, arguments, vault_path=None):
    """Run a single MCP tool call via subprocess. Returns parsed result."""
    vault = vault_path or VAULT_PATH
    env = {**os.environ, "SMART_VAULT_PATH": vault}

    init_msg = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "receptionist", "version": "0.1.0"}
        }
    }) + "\n"

    tool_msg = json.dumps({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        }
    }) + "\n"

    try:
        # Send both messages via stdin, then close it
        input_data = init_msg + tool_msg

        result = subprocess.run(
            ["node", MCP_SERVER_PATH],
            input=input_data,
            capture_output=True,
            text=True,
            timeout=30,
            env=env
        )

        # Parse stdout for our tool response (id: 2)
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                msg = json.loads(line)
                if msg.get("id") == 2:
                    return msg.get("result", msg)
            except json.JSONDecodeError:
                continue
        return None
    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        print(f"MCP error: {e}", file=__import__('sys').stderr)
        return None


def _parse_content(result):
    """Extract text content from MCP result."""
    if not result:
        return None
    if isinstance(result, dict) and "content" in result:
        content = result["content"]
        if isinstance(content, list) and len(content) > 0:
            text = content[0].get("text", "")
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
    return result


def preprocess_query(question):
    """Convert a natural language question into keyword search terms.
    Smart Connections embeddings work better with keywords than full questions."""
    import re
    # Normalize typos and common aliases
    aliases = {
        "req": "request",
        "reqs": "requests",
        "jobs": "tasks",
    }
    question = question.strip()
    for prefix in ["what is ", "what are ", "what's ", "who is ", "who are ",
                   "how does ", "how do ", "how to ", "why does ", "why do ",
                   "tell me about ", "tell en about ", "can you explain ", "explain ",
                   "describe ", "define "]:
        if question.lower().startswith(prefix):
            question = question[len(prefix):]
            break
    question = question.rstrip('?')
    # Remove filler words
    filler = r'\b(the|a|an|is|are|was|were|do|does|did|can|could|would|should|will|shall|may|might|this|that|these|those|my|your|our|their|it|its|we|you|they|i|me|him|her|us|them)\b'
    question = re.sub(filler, '', question, flags=re.IGNORECASE)
    question = re.sub(r'\s+', ' ', question).strip()
    return question if question else question


# Paths to exclude from RAG search — operational/meta files, not business knowledge
EXCLUDED_PATHS = [
    "Alfred/",
    "memory/",
    "MEMORY.md",
    "AGENTS.md",
    "SOUL.md",
    "IDENTITY.md",
    "USER.md",
    "TOOLS.md",
    "HEARTBEAT.md",
    "BOOTSTRAP.md",
    "SCARLETT-BRIEF.md",
    "Archive/",  # exclude ALL archive content (v1 research, old REQs, etc.)
    "Sources/",  # raw/source audit material; active receptionist layer lives outside Sources
    "_scripts/",
    ".obsidian/",
    "Reference/Alfred Toolkit-Boot.md",
    "Reference/AGENTS-Boot.md",
    "Reference/SOUL-Boot.md",
    "Reference/IDENTITY-Boot.md",
    "Reference/USER-Boot.md",
    "Reference/MEMORY-Boot.md",
    "Reference/TOOLS-Boot.md",
]


def _is_excluded(path):
    """Check if a note path should be excluded from RAG results."""
    # Also exclude any -Boot.md files (vault mirrors of workspace boot files)
    if path.endswith('-Boot.md'):
        return True
    for exc in EXCLUDED_PATHS:
        if path.startswith(exc) or path.endswith(exc) or f"/{exc}" in path:
            return True
    return False


def search(query, limit=MAX_CONTEXT_NOTES, threshold=SIMILARITY_THRESHOLD):
    """Search the vault and return notes with content.
    Tries Smart Connections first, then falls back to a local lexical search so
    customer vaults work before/without an embedding index.
    Excludes operational/meta paths and raw source archives.
    """
    # Preprocess query for better embedding match
    search_query = preprocess_query(query)
    if not search_query:
        search_query = query

    # Step 1: Try full preprocessed query
    search_data = _search_raw(search_query, limit, threshold)

    # Step 2: If no results, try with lower threshold
    if not search_data:
        search_data = _search_raw(search_query, limit, threshold - 0.05)

    # Step 3: If still no results, try individual words/terms
    if not search_data:
        words = search_query.split()
        if len(words) > 1:
            # Try the most specific word first (longest, least common)
            for word in sorted(words, key=len, reverse=True):
                if len(word) > 2:  # Skip tiny words
                    search_data = _search_raw(word, limit, threshold - 0.05)
                    if search_data:
                        break

    # Step 4: If still nothing, try the original unprocessed query
    if not search_data and search_query != query:
        search_data = _search_raw(query, limit, threshold - 0.05)

    if not search_data:
        return _local_search(query, limit)

    # Filter out excluded paths, then fetch content for remaining results
    filtered = []
    for note in search_data[:limit * 2]:  # Fetch more to account for exclusions
        path = note.get("path", "")
        if _is_excluded(path):
            continue
        filtered.append(note)
        if len(filtered) >= limit:
            break

    # Fetch content for top results
    enriched = []
    for note in filtered:
        path = note.get("path", "")
        score = note.get("similarity", 0)

        if not path:
            continue

        content_result = _run_mcp_tool("get_note_content", {
            "note_path": path
        })

        content_data = _parse_content(content_result)
        note_text = ""
        if isinstance(content_data, dict):
            note_text = content_data.get("content", content_data.get("text", content_data.get("body", str(content_data))))
        elif isinstance(content_data, str):
            note_text = content_data

        enriched.append({
            "path": path,
            "score": score,
            "content": note_text
        })

    # Smart Connections can rank broad hub notes above specific course sheets.
    # Merge in local lexical results so content questions can reach formation pages.
    local = _local_search(query, limit)
    combined = []
    seen = set()
    content_intent = any(t in _terms(query) for t in ["contenu", "objectifs", "anatomie", "aromatherapie", "ethique", "suedois", "stages"])
    for row in (local + enriched) if content_intent else (enriched + local):
        path = row.get("path", "")
        if not path or path in seen:
            continue
        seen.add(path)
        combined.append(row)
    return combined[:limit]


def _search_raw(query, limit=MAX_CONTEXT_NOTES, threshold=SIMILARITY_THRESHOLD):
    """Raw search without fallback logic. Returns parsed results list or None."""
    search_result = _run_mcp_tool("search_notes", {
        "query": query,
        "limit": limit,
        "threshold": max(threshold, 0.1)  # Never go below 0.1
    })

    data = _parse_content(search_result)
    if data and isinstance(data, list) and len(data) > 0:
        return data
    return None


def _norm(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower()


def _terms(query):
    stop = {
        "le", "la", "les", "un", "une", "des", "du", "de", "d", "a", "au", "aux",
        "je", "tu", "vous", "nous", "il", "elle", "ils", "elles", "me", "m", "te", "t",
        "ce", "cet", "cette", "ces", "que", "quoi", "qui", "quel", "quelle", "quels", "quelles",
        "est", "sont", "offrez", "offre", "puis", "peux", "peut", "comment", "combien",
        "sur", "pour", "par", "avec", "dans", "en", "et", "ou", "vos", "votre", "mes", "mon",
    }
    words = re.findall(r"[a-zA-ZÀ-ÿ0-9]+", _norm(query))
    terms = [w for w in words if len(w) > 2 and w not in stop]
    # Intent synonyms for AMS reception routing.
    if any(w in terms for w in ["coute", "cout", "prix", "tarif", "frais"]):
        terms.extend(["prix", "formation", "niveau", "praticien"])
    if any(w in terms for w in ["cours", "formations", "formation", "programme", "programmes"]):
        terms.extend(["parcours", "niveau", "praticien", "service", "reception"])
    if any(w in terms for w in ["carte", "continue", "continues", "ponctuel", "ponctuels"]):
        terms.extend(["formation", "continue", "carte", "liste", "vacuotherapie", "aromatherapie", "myofasciales", "taping", "cranio"])
    if any(w in terms for w in ["praticien", "praticienne", "massotherapeute", "massage", "deja", "400h"]):
        terms.extend(["parcours", "niveau", "niveau", "600", "7345", "kinesitherapie", "sportif", "anti", "stress"])
    if any(w in terms for w in ["contenu", "apprend", "apprendre", "detail", "details", "objectif", "objectifs", "matiere", "matieres"]):
        terms.extend(["contenu", "objectifs", "anatomie", "aromatherapie", "ethique", "suedois", "stages", "niveau", "praticien"])
    # Follow-up replies like "je débute" need the service flow + pathway, not a random page.
    if any(w in terms for w in ["debute", "debutant", "nouveau", "nouvelle", "commence", "commencer"]):
        terms.extend(["parcours", "service", "reception", "niveau", "praticien"])
    return terms


def _local_markdown_files():
    vault = Path(VAULT_PATH).expanduser()
    if not vault.exists():
        return []
    files = []
    for p in vault.rglob("*.md"):
        rel = p.relative_to(vault).as_posix()
        if _is_excluded(rel):
            continue
        files.append((rel, p))
    return files


def _local_search(query, limit=MAX_CONTEXT_NOTES):
    terms = _terms(query)
    if not terms:
        return []
    results = []
    for rel, p in _local_markdown_files():
        try:
            text = p.read_text(errors="ignore")
        except OSError:
            continue
        hay = _norm(rel + "\n" + text)
        title = _norm(rel)
        score = 0.0
        for term in terms:
            count = hay.count(term)
            if count:
                score += min(count, 12) * 0.08
                if term in title:
                    score += 0.5
        # Small boost for active AMS receptionist guidance and hubs.
        if rel.startswith("Réception Scarlett/"):
            score += 0.15
        # Course/price routing should prefer the human-guided main pathway.
        rel_norm = _norm(rel)
        course_intent = any(t in terms for t in ["coute", "cout", "prix", "tarif", "frais", "cours", "formation", "formations", "programme", "programmes", "parcours"])
        if course_intent and "parcours principal des formations" in rel_norm:
            score += 2.0
        if course_intent and "sequence de service reception" in rel_norm:
            score += 1.8
        if course_intent and "niveau-1-praticien" in rel_norm:
            score += 1.0
        trained_intent = any(t in terms for t in ["praticien", "praticienne", "massotherapeute", "400h", "deja", "kinesitherapie"])
        if trained_intent and "niveau-2-masso-kinesitherapie-specialisation-en-sportif" in rel_norm:
            score += 2.8
        if trained_intent and "niveau-2-massotherapie-avancee-specialisation-anti-stress" in rel_norm:
            score += 2.6
        if trained_intent and "niveau-3-orthotherapie-avancee" in rel_norm:
            score += 1.4
        a_la_carte_intent = any(t in terms for t in ["carte", "continue", "continues", "ponctuel", "ponctuels"])
        if trained_intent and any(x in rel_norm for x in ["vacuotherapie", "mise-a-niveau", "formation-continue-a-la-carte", "flushmassage"]):
            score += 1.0 if a_la_carte_intent else -0.8
        if a_la_carte_intent and "formation-continue-a-la-carte" in rel_norm:
            score += 3.0
        if a_la_carte_intent and "formations/" in rel_norm and any(x in rel_norm for x in ["aromatherapie", "vacuotherapie", "myofasciales", "taping", "cranio", "massage", "decongestion", "lymphatique", "ethique"]):
            score += 1.0
        content_intent = any(t in terms for t in ["contenu", "objectifs", "anatomie", "aromatherapie", "ethique", "suedois", "stages"])
        if content_intent and "niveau-1-praticien" in rel_norm:
            score += 3.0
        if content_intent and "formations/" in rel_norm:
            score += 0.8
        if score > 0:
            results.append({
                "path": rel,
                "score": score,
                "content": text[:6000],
            })
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]


def stats():
    """Get knowledge base statistics."""
    result = _run_mcp_tool("get_stats", {})
    parsed = _parse_content(result)
    if parsed:
        return parsed
    files = _local_markdown_files()
    return {
        "totalNotes": len(files),
        "totalBlocks": None,
        "embeddingDimension": None,
        "modelKey": "local lexical fallback",
    }