"""
Receptionist Bot — FastAPI RAG Service

Vault-grounded Q&A. Zero hallucination.
"""
import time
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from contextlib import asynccontextmanager

from config import (
    VAULT_PATH, OLLAMA_MODEL, SIMILARITY_THRESHOLD,
    MAX_CONTEXT_NOTES, MAX_CONTEXT_CHARS, RESPONSE_LANGUAGE,
    HOST, PORT
)
from ollama_client import generate, check_ollama
from prompt import build_context, build_prompt, get_refusal
from logger import init_db, log_interaction, get_recent_interactions, get_unanswered
from mcp_client import search as mcp_search, stats as mcp_stats

app = FastAPI(title="Receptionist Bot", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str
    language: Optional[str] = None
    threshold: Optional[float] = None
    max_notes: Optional[int] = None

class AskResponse(BaseModel):
    answer: str
    sources: list
    top_score: float
    refused: bool
    model: str
    latency_ms: int


@asynccontextmanager
async def lifespan(app):
    init_db()
    ollama_ok = check_ollama()
    if not ollama_ok:
        print(f"WARNING: Ollama model {OLLAMA_MODEL} not found!", flush=True)
    else:
        print(f"Ollama model {OLLAMA_MODEL} ready", flush=True)
    yield

app.router.lifespan_context = lifespan


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    """Ask a question, get a grounded answer."""
    lang = request.language or RESPONSE_LANGUAGE
    threshold = request.threshold or SIMILARITY_THRESHOLD
    max_notes = request.max_notes or MAX_CONTEXT_NOTES
    
    start = time.time()
    
    # 1. Search vault (run in thread pool to avoid blocking async loop)
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(
        None, mcp_search, request.question, max_notes, threshold
    )
    
    # 2. No results = refuse
    if not results:
        refusal = get_refusal(lang)
        latency = int((time.time() - start) * 1000)
        log_interaction(
            question=request.question, language=lang, top_score=0,
            sources=[], answer=refusal, refused=True,
            model=OLLAMA_MODEL, latency_ms=latency
        )
        return AskResponse(
            answer=refusal, sources=[], top_score=0,
            refused=True, model=OLLAMA_MODEL, latency_ms=latency
        )
    
    top_score = results[0].get("score", 0)
    
    # 3. Build context
    context = build_context(results)
    
    # 4. Generate grounded answer (run in thread pool)
    system_prompt, full_prompt = build_prompt(request.question, context, lang)
    
    answer = await loop.run_in_executor(
        None, generate, full_prompt, system_prompt, 0.1, 1024
    )
    
    if answer is None:
        answer = get_refusal(lang) + " (generation error)"
    
    latency = int((time.time() - start) * 1000)
    sources = [r.get("path", "") for r in results]
    
    log_interaction(
        question=request.question, language=lang, top_score=top_score,
        sources=sources, answer=answer, refused=False,
        model=OLLAMA_MODEL, latency_ms=latency
    )
    
    return AskResponse(
        answer=answer, sources=sources, top_score=top_score,
        refused=False, model=OLLAMA_MODEL, latency_ms=latency
    )


@app.get("/stats")
async def stats():
    """Get knowledge base statistics."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, mcp_stats)


@app.get("/logs")
async def logs(limit: int = 20):
    """Get recent interaction logs."""
    return get_recent_interactions(limit)


@app.get("/unanswered")
async def unanswered(limit: int = 20):
    """Get refused questions (below threshold) — for the learning loop."""
    return get_unanswered(limit)


@app.get("/health")
async def health():
    """Health check."""
    ollama = check_ollama()
    return {
        "status": "ok" if ollama else "degraded",
        "model": OLLAMA_MODEL,
        "ollama": ollama,
        "vault": VAULT_PATH,
        "threshold": SIMILARITY_THRESHOLD
    }


if __name__ == "__main__":
    import uvicorn
    init_db()
    uvicorn.run(app, host=HOST, port=PORT)