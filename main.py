"""
Receptionist Bot — FastAPI RAG Service

Vault-grounded Q&A. Zero hallucination.
"""
import time
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Any
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
from handoff_layer import answer_handoff
from student_support_layer import answer_current_student
from scarlett_core.brain import BrainTrace, SCARLETT_BRAIN_CONTRACT, maybe_log_review, get_review_queue
from scarlett_core.brain.timing.service_tiles import select_service_tile, select_service_tile_by_path, tile_catalog
from scarlett_core.brain.polish.intent_stats import classify_intent_trace, init_intent_stats_db, log_intent_event, summarize_intent_stats
from scarlett_core.brain.polish.response_families import family_catalog, polish_answer

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
    voice: Optional[dict[str, Any]] = None


@asynccontextmanager
async def lifespan(app):
    init_db()
    init_intent_stats_db()
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


def answer_internal_source_request(question: str) -> Optional[str]:
    q = _norm_question(question)
    import re
    phrase_terms = (
        "notes internes", "base de connaissances", "documents internes", "system prompt",
        "smart connections", ".md", "/users/",
    )
    token_terms = ("source", "sources", "fichier", "fichiers", "vault", "prompt", "rag")
    phrase_hit = any(term in q for term in phrase_terms)
    token_hit = any(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", q) for term in token_terms)
    if not (phrase_hit or token_hit):
        return None
    return (
        "Je ne peux pas afficher d’information interne. "
        "Par contre, je peux vous répondre clairement sur les formations, les prix, les campus, "
        "les modalités d’inscription ou le parcours qui convient le mieux à votre situation."
    )


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


def _polish_service_deflections(answer: str) -> str:
    """Remove lazy website-style deflections from generated replies."""
    import re
    if not answer:
        return answer
    polished = answer
    bad_sentence_patterns = [
        r"[^.!?\n]*(?:consultez|consulter|allez sur|aller sur|visitez|visiter)[^.!?\n]*(?:site web|site internet|site de l['’]AMS|site officiel)[^.!?\n]*[.!?] ?",
        r"[^.!?\n]*(?:sur le site web|sur le site internet|sur le site officiel)[^.!?\n]*(?:vous trouverez|vous pourrez trouver|il y a)[^.!?\n]*[.!?] ?",
        r"[^.!?\n]*je n['’]ai pas (?:la liste détaillée|le détail complet|ces détails)[^.!?\n]*(?:site web|site internet|conseiller)[^.!?\n]*[.!?] ?",
    ]
    for pat in bad_sentence_patterns:
        polished = re.sub(pat, "", polished, flags=re.IGNORECASE).strip()
    polished = re.sub(r"\n{3,}", "\n\n", polished).strip()
    if not polished:
        return (
            "Je peux vous orienter directement avec les informations AMS disponibles. "
            "Pour une disponibilité exacte, une date précise ou un dossier personnel, il faut ensuite confirmer avec l’AMS."
        )
    return polished


def finish_brain_answer(
    *,
    trace: BrainTrace,
    question: str,
    language: str,
    top_score: float,
    sources: list,
    answer: str,
    refused: bool,
    model: str,
    latency_ms: int,
    voice: Optional[dict[str, Any]] = None,
) -> AskResponse:
    """Shared answer finalizer: normal log + Brain review queue."""
    answer = _polish_service_deflections(answer)
    log_interaction_sources = sources if isinstance(sources, list) else [sources]
    source_layer = log_interaction_sources[0] if log_interaction_sources else None
    intent_trace = (voice or {}).get("_intent_trace")
    polished_meta = None
    try:
        answer, polished_meta = polish_answer(
            answer=answer, intent=getattr(intent_trace, "intent", None), question=question,
            source_layer=source_layer, model=model, top_score=top_score,
        )
    except Exception as exc:
        trace.add("response_polish", "failed", error=str(exc))
    if polished_meta:
        trace.add("response_polish", "applied", **polished_meta)
        if voice is not None:
            voice["response_polish"] = polished_meta
    log_interaction(
        question=question, language=language, top_score=top_score,
        sources=sources, answer=answer, refused=refused, model=model, latency_ms=latency_ms
    )
    try:
        log_intent_event(
            question=question, language=language, source_layer=source_layer,
            model=model, latency_ms=latency_ms, trace=intent_trace
        )
    except Exception as exc:
        trace.add("intent_stats", "log_failed", error=str(exc))
    trace.add(
        "answer", "complete", source=model, score=top_score,
        source_count=len(sources), latency_ms=latency_ms, refused=refused,
        voice_strategy=(voice or {}).get("strategy")
    )
    reviewed = maybe_log_review(
        trace, answer=answer, sources=sources, top_score=top_score,
        refused=refused, model=model, latency_ms=latency_ms
    )
    trace.add("review", "queued" if reviewed else "clear")
    public_voice = None
    if voice is not None:
        public_voice = dict(voice)
        public_voice.pop("_intent_trace", None)
    return AskResponse(
        answer=answer, sources=sources, top_score=top_score,
        refused=refused, model=model, latency_ms=latency_ms, voice=public_voice
    )

@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    """Ask a question, get a grounded answer."""
    lang = request.language or RESPONSE_LANGUAGE
    threshold = request.threshold or SIMILARITY_THRESHOLD
    max_notes = request.max_notes or MAX_CONTEXT_NOTES

    start = time.time()
    trace = BrainTrace.start(request.question, lang, conversation_context=request.conversation_context)
    trace.add("sources", "ready", source="customer_instance", vault_path=VAULT_PATH)
    trace.add("vault", "ready", source="smart_connections", max_notes=max_notes, threshold=threshold)
    intent_trace = classify_intent_trace(request.question)
    service_tile = select_service_tile(request.question)
    # Only promote a classified path into a spoken fast-path when the classifier
    # is genuinely confident. Low Jaccard/token-overlap matches caused stray
    # service tiles (e.g. “What is Scarlett?” becoming a greeting).
    confident_path_reason = (
        (intent_trace.reason or "").startswith("rule:")
        or intent_trace.reason in {"exact_alias", "phrase_contains"}
    )
    if (
        service_tile is None
        and intent_trace.path_id is not None
        and intent_trace.confidence >= 0.5
        and confident_path_reason
    ):
        service_tile = select_service_tile_by_path(intent_trace.path_id)
    voice = service_tile.voice_metadata() if service_tile else None
    if voice is None:
        voice = {}
    voice["_intent_trace"] = intent_trace
    voice["intent"] = intent_trace.intent
    voice["classified_path_id"] = intent_trace.path_id
    voice["classification_confidence"] = intent_trace.confidence
    voice["classification_reason"] = intent_trace.reason
    if voice.get("tile_id"):
        trace.add(
            "voice", "tile_selected",
            source="service_tiles",
            tile_id=voice.get("tile_id"),
            path_id=voice.get("path_id"),
            path_debug=voice.get("path_debug"),
            strategy=voice.get("strategy"),
            first_audio_ms=voice.get("first_audio_ms"),
        )
    trace.add(
        "intent", "classified", source="path_classifier",
        intent=intent_trace.intent, path_id=intent_trace.path_id,
        confidence=intent_trace.confidence, reason=intent_trace.reason,
    )

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
        'who are you', 'what are you', 'what is scarlett', 'who is scarlett', 'introduce yourself', 'tell me about yourself',
        "what's your name", 'what is your name', 'your name', 'name',
        "c'est quoi ton nom", 'quel est ton nom', 'comment tu t’appelles', "comment tu t'appelles",
        'comment vous vous appelez', 'tu es qui', 'vous êtes qui', 'qui es-tu', 'qui êtes-vous',
    }
    if q_norm in greeting:
        answer = "Bonjour, je suis Scarlett. Ça va très bien, merci. Je peux vous aider avec les formations, les prix, les campus ou l'inscription à l'AMS."
        latency = int((time.time() - start) * 1000)
        trace.add("facts", "matched", source="local_identity_layer")
        return finish_brain_answer(trace=trace, question=request.question, language=lang, top_score=1, sources=["local_identity_layer"], answer=answer, refused=False, model="local", latency_ms=latency, voice=voice)
    if q_norm in identity:
        answer = "Je m’appelle Scarlett. Je suis la réception virtuelle de l’AMS."
        latency = int((time.time() - start) * 1000)
        trace.add("facts", "matched", source="local_identity_layer")
        return finish_brain_answer(trace=trace, question=request.question, language=lang, top_score=1, sources=["local_identity_layer"], answer=answer, refused=False, model="local", latency_ms=latency, voice=voice)

    # 0.54 Deterministic safety route for internal-source requests.
    internal_answer = answer_internal_source_request(request.question)
    if internal_answer:
        latency = int((time.time() - start) * 1000)
        trace.add("facts", "matched", source="local_safety_layer", score=1)
        return finish_brain_answer(trace=trace, question=request.question, language=lang, top_score=1, sources=["local_safety_layer"], answer=internal_answer, refused=False, model="local", latency_ms=latency, voice=voice)

    # 0.55 Deterministic customer-service “how does it work?” route.
    how_answer = answer_how_it_works(request.question)
    if how_answer:
        latency = int((time.time() - start) * 1000)
        trace.add("facts", "matched", source="local_service_confidence_layer", score=1)
        return finish_brain_answer(trace=trace, question=request.question, language=lang, top_score=1, sources=["local_service_confidence_layer"], answer=how_answer, refused=False, model="local", latency_ms=latency, voice=voice)

    # 0.56 Deterministic current-student support route.
    current_student_answer = answer_current_student(request.question)
    if current_student_answer:
        latency = int((time.time() - start) * 1000)
        trace.add("facts", "matched", source="local_current_student_layer", score=1)
        return finish_brain_answer(trace=trace, question=request.question, language=lang, top_score=1, sources=["local_current_student_layer"], answer=current_student_answer, refused=False, model="local", latency_ms=latency, voice=voice)

    # 0.6 Deterministic local campus/location route.
    # Fixed campus data should be answered confidently without pretending live web/maps are needed.
    location_answer = answer_location(request.question)
    if location_answer:
        latency = int((time.time() - start) * 1000)
        trace.add("facts", "matched", source="local_location_layer", score=1)
        return finish_brain_answer(trace=trace, question=request.question, language=lang, top_score=1, sources=["local_location_layer"], answer=location_answer, refused=False, model="local", latency_ms=latency, voice=voice)

    # 0.7 Deterministic pricing/financing route.
    # Common totals and weekly payment amounts should be arithmetic, not inferred by the LLM.
    pricing_answer = answer_pricing(request.question, getattr(request, "conversation_context", "") or "")
    if pricing_answer:
        latency = int((time.time() - start) * 1000)
        trace.add("facts", "matched", source="local_pricing_layer", score=1)
        return finish_brain_answer(trace=trace, question=request.question, language=lang, top_score=1, sources=["local_pricing_layer"], answer=pricing_answer, refused=False, model="local", latency_ms=latency, voice=voice)

    # 0.8 Deterministic à-la-carte list route.
    continuing_ed_question = request.question
    ctx_norm = _norm_question(getattr(request, "conversation_context", "") or "")
    q_norm_for_context = _norm_question(request.question)
    content_followup = any(x in q_norm_for_context for x in [
        "contenu", "dans le cours", "du cours", "apprend", "apprendre", "info sur le contenu", "plus d info", "plus info"
    ])
    if content_followup and any(x in ctx_norm for x in ["aromatherapie", "aromathérapie", "huiles essentielles", "huile essentielle"]):
        continuing_ed_question = f"{request.question} cours d'aromathérapie à la carte aromathérapie clinique"
    continuing_ed_answer = answer_continuing_ed(continuing_ed_question)
    if continuing_ed_answer:
        latency = int((time.time() - start) * 1000)
        trace.add("facts", "matched", source="local_continuing_ed_layer", score=1)
        return finish_brain_answer(trace=trace, question=request.question, language=lang, top_score=1, sources=["local_continuing_ed_layer"], answer=continuing_ed_answer, refused=False, model="local", latency_ms=latency, voice=voice)

    # 0.85 Deterministic handoff/contact route.
    # Scarlett should never pretend a transfer, callback, or email was actually
    # completed; she gives the official contact path and can prepare the request.
    handoff_answer = answer_handoff(request.question, getattr(request, "conversation_context", "") or "")
    if handoff_answer:
        latency = int((time.time() - start) * 1000)
        trace.add("facts", "matched", source="local_handoff_layer", score=1)
        return finish_brain_answer(trace=trace, question=request.question, language=lang, top_score=1, sources=["local_handoff_layer"], answer=handoff_answer, refused=False, model="local", latency_ms=latency, voice=voice)

    # 0.9 Fast-path service tile route for common voice-control/service moments.
    # These are intentionally short and interruptible; RAG is unnecessary for repair,
    # signup pre-checks, receipts, handoffs, and capability prompts.
    if service_tile and service_tile.line and service_tile.strategy in {"prebuilt_tile", "receipt", "lookup_line", "clarify", "handoff_or_escalate"}:
        latency = int((time.time() - start) * 1000)
        trace.add("facts", "matched", source="local_service_tile_layer", score=1, tile_id=service_tile.tile_id)
        return finish_brain_answer(trace=trace, question=request.question, language=lang, top_score=1, sources=["local_service_tile_layer"], answer=service_tile.line, refused=False, model="local", latency_ms=latency, voice=voice)

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
        trace.add("retrieval", "miss", source="vault", score=0)
        return finish_brain_answer(trace=trace, question=request.question, language=lang, top_score=0, sources=[], answer=answer, refused=False, model=OLLAMA_MODEL, latency_ms=latency, voice=voice)

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

    trace.add("retrieval", "matched", source="vault", score=top_score, source_count=len(sources))
    return finish_brain_answer(trace=trace, question=request.question, language=lang, top_score=top_score, sources=sources, answer=answer, refused=False, model=OLLAMA_MODEL, latency_ms=latency, voice=voice)


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


@app.get("/brain/contract")
async def brain_contract():
    """Return Scarlett Brain v1 product contract."""
    return SCARLETT_BRAIN_CONTRACT


@app.get("/brain/review-queue")
async def brain_review_queue(limit: int = 50):
    """Return weak answers queued for human review/tuning."""
    return get_review_queue(limit)


@app.get("/brain/service-tiles")
async def brain_service_tiles():
    """Return scripted fast-path voice tiles for common AMS interactions."""
    return {"count": len(tile_catalog()), "tiles": tile_catalog()}


@app.get("/brain/intent-stats")
async def brain_intent_stats(limit: int = 500):
    """Return most-used intent/path patterns for the polish loop."""
    return summarize_intent_stats(limit=limit)


@app.get("/brain/response-families")
async def brain_response_families():
    """Return polished response family scaffolds and emotional scopes."""
    return family_catalog()


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