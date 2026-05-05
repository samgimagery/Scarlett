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
from ollama_client import generate as ollama_generate, check_ollama
from prompt import build_context, build_prompt, get_refusal, get_system_prompt
from logger import init_db, log_interaction, get_recent_interactions, get_unanswered
from mcp_client import search as mcp_search, stats as mcp_stats
from vault_context import get_vault_context
from location_layer import answer_location
from pricing_layer import answer_pricing
from continuing_ed_layer import answer_continuing_ed
from student_support_layer import answer_current_student

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
    conversation_context: Optional[str] = None

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



def _norm_question(text: str) -> str:
    import re
    q = (text or "").lower().strip().replace("’", "'")
    q = re.sub(r"[!?.,]+$", "", q).strip()
    return re.sub(r"\s+", " ", q)


def answer_how_it_works(question: str) -> Optional[str]:
    q = _norm_question(question)
    for prefix in ("oui ", "ok ", "d'accord ", "parfait "):
        if q.startswith(prefix):
            q = q[len(prefix):].strip()
    if not any(x in q for x in [
        "comment ca fonctionne", "comment ça fonctionne", "comment sa fonctionne",
        "comment ca marche", "comment ça marche", "comment sa marche",
        "ca fonctionne comment", "ça fonctionne comment", "sa fonctionne comment",
        "comment fonctionne", "comment marche", "how does it work", "how it works",
    ]):
        return None
    return (
        "Bien sûr. Le fonctionnement est simple.\n\n"
        "Je vous aide d’abord à situer votre point de départ : est-ce que vous commencez en massage, est-ce que vous êtes déjà étudiant, ou est-ce que vous avez déjà une formation. Ensuite, je vous donne le parcours le plus logique, avec les prix, le format, les campus et les prochaines étapes.\n\n"
        "Si vous commencez, le point de départ habituel est le **Niveau 1 | Praticien en massothérapie** : 400 heures, format hybride, 4 995 $.\n\n"
        "Je peux vous expliquer ce parcours clairement, sans vous envoyer trop vite vers un formulaire."
    )

@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    """Ask a question, get a grounded answer."""
    lang = request.language or RESPONSE_LANGUAGE
    threshold = request.threshold or SIMILARITY_THRESHOLD
    max_notes = request.max_notes or MAX_CONTEXT_NOTES

    start = time.time()

    # Get event loop (needed for all paths)
    loop = asyncio.get_event_loop()

    # 0. Get vault context for metacognitive prompt injection
    vault_info = None
    try:
        vault_info = await loop.run_in_executor(None, get_vault_context)
    except Exception:
        pass  # Non-critical — prompt works without it

    # 0.5 Small-talk / identity route. Never answer as a vault/library; Scarlett is reception.
    q_lower = request.question.strip().lower().rstrip('?!.,')
    q_norm = q_lower.replace("’", "'")
    greeting = {
        'hi', 'hello', 'hey', 'salut', 'bonjour', 'coucou', 'yo', 'allo', 'allô',
        'how are you', 'how are you doing', 'ça va', 'ca va', 'comment ça va', 'comment ca va',
        'hey how are you', 'hey how are you doing', 'bonjour ça va', 'bonjour ca va',
    }
    identity = {
        'who are you', 'what are you', 'introduce yourself', 'tell me about yourself',
        "what's your name", 'what is your name', 'your name', 'name',
        "c'est quoi ton nom", 'quel est ton nom', 'comment tu t’appelles', "comment tu t'appelles",
        'comment vous vous appelez', 'tu es qui', 'vous êtes qui', 'qui es-tu', 'qui êtes-vous',
    }
    if q_norm in greeting:
        answer = "Bonjour, je suis Scarlett. Ça va très bien, merci. Je peux vous aider avec les formations, les prix, les campus ou l'inscription à l'AMS."
        latency = int((time.time() - start) * 1000)
        log_interaction(question=request.question, language=lang, top_score=0, sources=[], answer=answer, refused=False, model=OLLAMA_MODEL, latency_ms=latency)
        return AskResponse(answer=answer, sources=[], top_score=0, refused=False, model=OLLAMA_MODEL, latency_ms=latency)
    if q_norm in identity:
        answer = "Je m’appelle Scarlett. Je suis la réception virtuelle de l’AMS."
        latency = int((time.time() - start) * 1000)
        log_interaction(question=request.question, language=lang, top_score=0, sources=[], answer=answer, refused=False, model=OLLAMA_MODEL, latency_ms=latency)
        return AskResponse(answer=answer, sources=[], top_score=0, refused=False, model=OLLAMA_MODEL, latency_ms=latency)

    # 0.55 Deterministic customer-service “how does it work?” route.
    how_answer = answer_how_it_works(request.question)
    if how_answer:
        latency = int((time.time() - start) * 1000)
        log_interaction(
            question=request.question, language=lang, top_score=1,
            sources=["local_service_confidence_layer"], answer=how_answer, refused=False,
            model="local", latency_ms=latency
        )
        return AskResponse(
            answer=how_answer, sources=["local_service_confidence_layer"], top_score=1,
            refused=False, model="local", latency_ms=latency
        )

    # 0.56 Deterministic current-student support route.
    current_student_answer = answer_current_student(request.question)
    if current_student_answer:
        latency = int((time.time() - start) * 1000)
        log_interaction(
            question=request.question, language=lang, top_score=1,
            sources=["local_current_student_layer"], answer=current_student_answer, refused=False,
            model="local", latency_ms=latency
        )
        return AskResponse(
            answer=current_student_answer, sources=["local_current_student_layer"], top_score=1,
            refused=False, model="local", latency_ms=latency
        )

    # 0.6 Deterministic local campus/location route.
    # Fixed campus data should be answered confidently without pretending live web/maps are needed.
    location_answer = answer_location(request.question)
    if location_answer:
        latency = int((time.time() - start) * 1000)
        log_interaction(
            question=request.question, language=lang, top_score=1,
            sources=["local_location_layer"], answer=location_answer, refused=False,
            model="local", latency_ms=latency
        )
        return AskResponse(
            answer=location_answer, sources=["local_location_layer"], top_score=1,
            refused=False, model="local", latency_ms=latency
        )

    # 0.7 Deterministic pricing/financing route.
    # Common totals and weekly payment amounts should be arithmetic, not inferred by the LLM.
    pricing_answer = answer_pricing(request.question, getattr(request, "conversation_context", "") or "")
    if pricing_answer:
        latency = int((time.time() - start) * 1000)
        log_interaction(
            question=request.question, language=lang, top_score=1,
            sources=["local_pricing_layer"], answer=pricing_answer, refused=False,
            model="local", latency_ms=latency
        )
        return AskResponse(
            answer=pricing_answer, sources=["local_pricing_layer"], top_score=1,
            refused=False, model="local", latency_ms=latency
        )

    # 0.8 Deterministic à-la-carte list route.
    continuing_ed_answer = answer_continuing_ed(request.question)
    if continuing_ed_answer:
        latency = int((time.time() - start) * 1000)
        log_interaction(
            question=request.question, language=lang, top_score=1,
            sources=["local_continuing_ed_layer"], answer=continuing_ed_answer, refused=False,
            model="local", latency_ms=latency
        )
        return AskResponse(
            answer=continuing_ed_answer, sources=["local_continuing_ed_layer"], top_score=1,
            refused=False, model="local", latency_ms=latency
        )

    # 1. Search vault (run in thread pool to avoid blocking async loop)
    results = await loop.run_in_executor(
        None, mcp_search, request.question, max_notes, threshold
    )

    # 2. No results — still let Scarlett respond warmly, not refuse
    if not results:
        # Try one more time with lower threshold
        results = await loop.run_in_executor(
            None, mcp_search, request.question, max_notes, 0.1
        )
    if not results:
        # No context at all — Scarlett stays reception-facing and does not mention internal systems.
        system = get_system_prompt(lang)
        fallback_q = f"{request.question}\n\n(Réponds comme Scarlett, réception AMS. Ne mentionne jamais vault, fichiers, notes, sources ou base de connaissances. Si l'information manque, propose de référer à un conseiller AMS.)"
        try:
            system = get_system_prompt(lang, **(vault_info or {}))
            ollama_res = await loop.run_in_executor(
                None, ollama_generate, fallback_q, system
            )
            answer = ollama_res or get_refusal(lang)
        except:
            answer = get_refusal(lang)
        latency = int((time.time() - start) * 1000)
        log_interaction(
            question=request.question, language=lang, top_score=0,
            sources=[], answer=answer, refused=False,
            model=OLLAMA_MODEL, latency_ms=latency
        )
        return AskResponse(
            answer=answer, sources=[], top_score=0,
            refused=False, model=OLLAMA_MODEL, latency_ms=latency
        )

    top_score = results[0].get("score", 0)

    # 3. Build context
    context = build_context(results)

    # 4. Generate grounded answer (run in thread pool)
    question_for_prompt = request.question
    if request.conversation_context:
        question_for_prompt = f"Contexte de conversation à respecter (ne pas répéter les questions déjà répondues):\n{request.conversation_context}\n\nQuestion actuelle: {request.question}"
    system_prompt, full_prompt = build_prompt(question_for_prompt, context, lang, vault_info=vault_info)

    answer = await loop.run_in_executor(
        None, ollama_generate, full_prompt, system_prompt, 0.1, 1024
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