"""
Vault Context — gathers metacognitive context for the librarian prompt.

Builds a snapshot of what the active vault holds, what's recent, and what
connects. Uses the file tree (not RAG block count) so the number matches what
users see in the constellation.
"""
import json
import urllib.request
import urllib.error
from pathlib import Path
from config import VAULT_PATH

MC_VAULT_URL = "http://127.0.0.1:8787/api/vault/tree"

# Categories to skip — operational/meta files, not knowledge content
EXCLUDED_CATEGORIES = {"Archive", "Alfred", "Templates", "memory", ".obsidian"}

# Cache: fetch once per 5 minutes (vault structure changes slowly)
_cache = None
_cache_age = 0
CACHE_TTL = 300


def _fetch_json(url, timeout=5):
    """Fetch JSON from a URL, return parsed data or None."""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError):
        return None


def _get_vault_tree():
    """Return active vault files.

    Mission Control has a richer API tree, but customer vaults are ordinary
    Obsidian folders. Read them directly so Scarlett follows
    RECEPTIONIST_VAULT_PATH instead of accidentally describing Mission Control.
    """
    vault = Path(VAULT_PATH).expanduser()
    if vault.exists():
        files = []
        for p in vault.rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(vault).as_posix()
            try:
                stat = p.stat()
            except OSError:
                continue
            files.append({
                "path": rel,
                "name": p.name,
                "modified": stat.st_mtime,
                "created": stat.st_ctime,
            })
        return files

    data = _fetch_json(MC_VAULT_URL)
    if data and isinstance(data, dict):
        return data.get("files", [])
    return []


def get_vault_context():
    """Build vault context dict for prompt injection.

    Returns dict with: note_count, categories, top_categories, recent_work
    Note count matches what the constellation shows (actual .md files, not RAG blocks).
    """
    global _cache, _cache_age
    import time

    now = time.time()
    if _cache and (now - _cache_age) < CACHE_TTL:
        return _cache

    files = _get_vault_tree()

    # Filter to .md files, exclude operational categories
    md_files = []
    for f in files:
        if not isinstance(f, dict):
            continue
        path = f.get("path", "")
        if not (path.endswith(".md") or path.endswith(".txt")):
            continue
        cat = path.split("/")[0] if "/" in path else "root"
        if cat in EXCLUDED_CATEGORIES:
            continue
        # Skip boot mirrors
        if path.endswith("-Boot.md"):
            continue
        name = f.get("name", path.split("/")[-1])
        # Skip short content (< 50 chars, likely stubs)
        content = f.get("content", "")
        # We don't have content here, so just count the file
        md_files.append(f)

    # Build category counts from filtered files
    cats = {}
    for f in md_files:
        path = f.get("path", "") if isinstance(f, dict) else str(f)
        cat = path.split("/")[0] if "/" in path else "root"
        cats[cat] = cats.get(cat, 0) + 1

    # Sort by size — top categories
    sorted_cats = sorted(cats.items(), key=lambda x: -x[1])
    category_list = ", ".join(f"{name} ({count})" for name, count in sorted_cats[:8])
    top_cats = ", ".join(f"{name}" for name, count in sorted_cats[:3])

    # Find recent work — files with recent modification
    recent = []
    for f in md_files:
        path = f.get("path", "")
        cat = path.split("/")[0] if "/" in path else "root"
        if cat in EXCLUDED_CATEGORIES or cat == "root":
            continue
        modified = f.get("modified", f.get("created", ""))
        name = path.split("/")[-1].replace(".md", "")
        if len(name) > 3:
            recent.append((modified or "", name))

    recent.sort(key=lambda x: x[0], reverse=True)
    recent_work = ", ".join(name for _, name in recent[:5]) if recent else "various projects"

    # Note count: actual filtered .md files (matches constellation display)
    note_count = len(md_files)

    result = {
        "note_count": note_count,
        "categories": category_list,
        "top_categories": top_cats,
        "recent_work": recent_work,
    }

    _cache = result
    _cache_age = now
    return result