"""
MCP Client — communicates with Smart Connections MCP server via subprocess + JSON-RPC.

Uses line-by-line reading to properly handle the init → tool call sequence.
"""
import json
import subprocess
import time
import os
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


def search(query, limit=MAX_CONTEXT_NOTES, threshold=SIMILARITY_THRESHOLD):
    """Search the vault and return notes with content.
    Tries the full query first, then falls back to shorter versions if no results."""
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
        return []
    
    # Fetch content for top results
    enriched = []
    for note in search_data[:limit]:
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
    
    return enriched


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


def stats():
    """Get knowledge base statistics."""
    result = _run_mcp_tool("get_stats", {})
    return _parse_content(result)