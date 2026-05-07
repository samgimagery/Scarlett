"""Polished response families for high-frequency Scarlett intents.

This is the controlled-performance layer Sam described: facts still come from
local layers/RAG, but the delivery shape can be selected from a small family of
human-polished variants by emotional scope.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any


EMOTIONAL_SCOPES = ("concise", "warm", "reassuring", "guiding", "repair")

DEFAULT_FACTS: dict[str, str] = {
    "price": "4 995 $",
    "weekly": "104 $",
    "price_n1": "4 995 $",
    "weekly_n1": "104 $",
    "price_n2": "7 345 $",
    "weekly_n2": "111 $",
    "price_n3": "3 595 $",
    "weekly_n3": "97 $",
    "total_n1_n2": "12 340 $",
    "total_all": "15 935 $",
    "admin_fee": "100 $",
}

SAFE_POLISH_INTENTS = {
    "aroma_course",
    "price_n1",
    "price_n2",
    "price_n3",
    "total_n1_n2",
    "total_all",
    "weekly",
    "financing",
    "too_expensive",
    "unsure_start",
    "human",
}

DETERMINISTIC_POLISH_SOURCES = {
    "local_pricing_layer",
    "local_continuing_ed_layer",
    "local_service_tile_layer",
    "telegram_local",
}


@dataclass(frozen=True)
class ResponseVariant:
    scope: str
    line: str
    use_when: str


@dataclass(frozen=True)
class ResponseFamily:
    intent: str
    fact_slots: tuple[str, ...]
    variants: tuple[ResponseVariant, ...]
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


FAMILIES: dict[str, ResponseFamily] = {
    "aroma_course": ResponseFamily(
        intent="aroma_course",
        fact_slots=("course_name", "category", "next_step"),
        notes="Continuing-ed route. Keep distinct from Niveau 1/Niveau 2 practitioner content.",
        variants=(
            ResponseVariant("concise", "Oui — l’AMS offre l’aromathérapie comme formation à la carte.", "fast confirmation"),
            ResponseVariant("warm", "Oui, absolument. L’aromathérapie fait partie des formations à la carte que je peux vous situer clairement.", "caller browsing options"),
            ResponseVariant("reassuring", "Oui — et je vais la garder séparée du parcours praticien, pour ne pas mélanger les contenus.", "after correction or confusion"),
            ResponseVariant("guiding", "Oui. Vous voulez surtout connaître le contenu, le prix, ou la prochaine étape pour l’aromathérapie?", "next-step prompt"),
            ResponseVariant("repair", "Vous avez raison — on parle bien de l’aromathérapie, pas du parcours praticien. Je reprends sur ce cours-là.", "explicit correction"),
        ),
    ),
    "price_n1": ResponseFamily(
        intent="price_n1",
        fact_slots=("level", "price", "weekly"),
        variants=(
            ResponseVariant("concise", "Le Niveau 1 est à {price}, ou à partir de {weekly} par semaine.", "direct price ask"),
            ResponseVariant("warm", "Oui — pour le Niveau 1, le repère principal est {price}, avec une option à partir de {weekly} par semaine.", "normal inquiry"),
            ResponseVariant("reassuring", "Je vous donne le chiffre simplement: le Niveau 1 est à {price}. On peut ensuite regarder les options de paiement.", "price anxiety"),
            ResponseVariant("guiding", "Le Niveau 1 est à {price}. Voulez-vous que je vous compare aussi avec le Niveau 2 ou le total du parcours?", "comparison opportunity"),
            ResponseVariant("repair", "Je reprends clairement: pour le Niveau 1, le prix est {price}.", "repeat/correction"),
        ),
    ),
    "price_n2": ResponseFamily(
        intent="price_n2",
        fact_slots=("level", "price_n2", "weekly_n2", "admin_fee"),
        notes="Professional Niveau 2 price. Lead with the main pathway, not à-la-carte alternatives.",
        variants=(
            ResponseVariant("concise", "Le Niveau 2 est à {price_n2}, ou à partir de {weekly_n2} par semaine.", "direct price ask"),
            ResponseVariant("warm", "Oui — pour le Niveau 2, le repère principal est {price_n2}, avec une option à partir de {weekly_n2} par semaine.", "normal inquiry"),
            ResponseVariant("reassuring", "Je vous donne le chiffre simplement: le Niveau 2 est à {price_n2}. On peut ensuite regarder le rythme de paiement.", "price anxiety"),
            ResponseVariant("guiding", "Le Niveau 2 est à {price_n2}. Si vous comparez, le Niveau 1 + Niveau 2 ensemble arrive à {total_n1_n2}.", "comparison opportunity"),
            ResponseVariant("repair", "Je reprends clairement: pour le Niveau 2, le prix est {price_n2}.", "repeat/correction"),
        ),
    ),
    "price_n3": ResponseFamily(
        intent="price_n3",
        fact_slots=("level", "price_n3", "weekly_n3", "admin_fee"),
        notes="Professional Niveau 3 price. Keep concise; it usually follows Niveau 2 context.",
        variants=(
            ResponseVariant("concise", "Le Niveau 3 est à {price_n3}, ou à partir de {weekly_n3} par semaine.", "direct price ask"),
            ResponseVariant("warm", "Oui — pour le Niveau 3, le repère principal est {price_n3}, avec une option à partir de {weekly_n3} par semaine.", "normal inquiry"),
            ResponseVariant("reassuring", "Je vous donne le chiffre simplement: le Niveau 3 est à {price_n3}.", "price anxiety"),
            ResponseVariant("guiding", "Le Niveau 3 est à {price_n3}. Pour le parcours complet des trois niveaux, le total est {total_all}.", "comparison opportunity"),
            ResponseVariant("repair", "Je reprends clairement: pour le Niveau 3, le prix est {price_n3}.", "repeat/correction"),
        ),
    ),
    "total_n1_n2": ResponseFamily(
        intent="total_n1_n2",
        fact_slots=("price_n1", "price_n2", "total_n1_n2", "admin_fee"),
        notes="Total for the first two professional levels.",
        variants=(
            ResponseVariant("concise", "Niveau 1 plus Niveau 2, le total est {total_n1_n2}.", "direct total ask"),
            ResponseVariant("warm", "Oui — Niveau 1 ({price_n1}) + Niveau 2 ({price_n2}) donne un total de {total_n1_n2}.", "normal inquiry"),
            ResponseVariant("reassuring", "Pour les deux premiers niveaux ensemble, prévoyez {total_n1_n2}. On peut ensuite regarder les options de paiement.", "budget check"),
            ResponseVariant("guiding", "Les deux premiers niveaux totalisent {total_n1_n2}. Le parcours complet avec Niveau 3 monte à {total_all}.", "comparison opportunity"),
            ResponseVariant("repair", "Je reprends le calcul: Niveau 1 + Niveau 2 = {total_n1_n2}.", "repeat/correction"),
        ),
    ),
    "total_all": ResponseFamily(
        intent="total_all",
        fact_slots=("price_n1", "price_n2", "price_n3", "total_all", "admin_fee"),
        notes="Total for all three professional levels.",
        variants=(
            ResponseVariant("concise", "Les trois niveaux ensemble totalisent {total_all}.", "direct total ask"),
            ResponseVariant("warm", "Oui — Niveau 1, Niveau 2 et Niveau 3 ensemble totalisent {total_all}.", "normal inquiry"),
            ResponseVariant("reassuring", "Pour le parcours complet des trois niveaux, le total est {total_all}. C’est un vrai investissement, donc ça vaut la peine de le regarder calmement.", "budget check"),
            ResponseVariant("guiding", "Le parcours complet totalise {total_all}. Si vous voulez avancer par étapes, Niveau 1 + Niveau 2 représente {total_n1_n2}.", "comparison opportunity"),
            ResponseVariant("repair", "Je reprends le total complet: les trois niveaux ensemble sont à {total_all}.", "repeat/correction"),
        ),
    ),
    "weekly": ResponseFamily(
        intent="weekly",
        fact_slots=("weekly_n1", "weekly_n2", "weekly_n3"),
        notes="Weekly payment anchors by level. If no level is specified, give all three anchors.",
        variants=(
            ResponseVariant("concise", "Les repères par semaine sont: Niveau 1 {weekly_n1}, Niveau 2 {weekly_n2}, Niveau 3 {weekly_n3}.", "direct weekly ask"),
            ResponseVariant("warm", "Oui — à titre de repère, le Niveau 1 commence à {weekly_n1}/semaine, le Niveau 2 à {weekly_n2}/semaine, et le Niveau 3 à {weekly_n3}/semaine.", "normal inquiry"),
            ResponseVariant("reassuring", "Pour regarder le budget calmement: Niveau 1 {weekly_n1}/semaine, Niveau 2 {weekly_n2}/semaine, Niveau 3 {weekly_n3}/semaine.", "budget check"),
            ResponseVariant("guiding", "Par semaine, les repères sont {weekly_n1}, {weekly_n2} et {weekly_n3} selon le niveau. Vous voulez que je parte du Niveau 1 ou d’un niveau précis?", "needs level clarification"),
            ResponseVariant("repair", "Je reprends les montants hebdomadaires: Niveau 1 {weekly_n1}, Niveau 2 {weekly_n2}, Niveau 3 {weekly_n3}.", "repeat/correction"),
        ),
    ),
    "financing": ResponseFamily(
        intent="financing",
        fact_slots=("weekly_n1", "financing_options"),
        notes="Financing/payment overview; avoid implying approval or guarantee.",
        variants=(
            ResponseVariant("concise", "Oui — il y a des options de paiement, dont des versements hebdomadaires et du financement possible via IFINANCE, la banque ou une marge de crédit partenaire.", "direct financing ask"),
            ResponseVariant("warm", "Oui. Scarlett peut vous donner les repères: paiements échelonnés, IFINANCE, banque ou marge de crédit partenaire selon la situation.", "normal inquiry"),
            ResponseVariant("reassuring", "Oui — on peut regarder ça sans vous presser. Les options connues sont les paiements échelonnés et du financement possible, à confirmer selon votre dossier.", "budget stress"),
            ResponseVariant("guiding", "Vous voulez que je vous donne le repère par semaine pour un niveau précis, ou les options générales de financement?", "branching next step"),
            ResponseVariant("repair", "Je reprends simplement: paiement échelonné possible, et financement possible via IFINANCE, banque ou marge de crédit partenaire.", "repeat/correction"),
        ),
    ),
    "too_expensive": ResponseFamily(
        intent="too_expensive",
        fact_slots=("payment_options", "lower_commitment_options"),
        variants=(
            ResponseVariant("concise", "Je comprends. On peut regarder les options de paiement ou des cours à plus petit engagement.", "short objection"),
            ResponseVariant("warm", "Je comprends — c’est un vrai investissement. Je peux vous aider à voir les options sans vous pousser.", "soft objection"),
            ResponseVariant("reassuring", "C’est normal de vouloir valider le budget avant d’avancer. On peut regarder les paiements et les alternatives plus légères.", "budget stress"),
            ResponseVariant("guiding", "Vous préférez que je vous montre les options de paiement, ou des cours plus courts et moins chers?", "branching next step"),
            ResponseVariant("repair", "D’accord — je mets le prix de côté une seconde et je vous aide à trouver l’option la plus réaliste.", "caller frustrated by cost"),
        ),
    ),
    "unsure_start": ResponseFamily(
        intent="unsure_start",
        fact_slots=("experience_level", "recommended_path"),
        variants=(
            ResponseVariant("concise", "Aucun souci — on part de votre expérience actuelle et je vous oriente vers le bon niveau.", "general unsure"),
            ResponseVariant("warm", "Bien sûr. On va le faire simplement: je situe d’abord votre point de départ, puis je vous donne le parcours logique.", "caller needs orientation"),
            ResponseVariant("reassuring", "C’est très normal d’être mélangé au début. Je vais vous aider à trier ça sans vous noyer d’information.", "overwhelmed caller"),
            ResponseVariant("guiding", "Vous avez déjà une formation en massage, ou vous commencez complètement?", "first clarification"),
            ResponseVariant("repair", "Je reprends plus simplement: la première question, c’est votre niveau d’expérience actuel.", "too much information"),
        ),
    ),
    "human": ResponseFamily(
        intent="human",
        fact_slots=("handoff_target", "prepared_context"),
        variants=(
            ResponseVariant("concise", "Bien sûr — je peux vous aider à préparer la bonne demande pour une personne de l’AMS.", "handoff"),
            ResponseVariant("warm", "Oui, bien sûr. Je peux d’abord noter le bon contexte pour que la personne vous réponde utilement.", "cooperative handoff"),
            ResponseVariant("reassuring", "Aucun problème — si vous préférez parler à quelqu’un, je vais vous orienter proprement.", "caller wants human"),
            ResponseVariant("guiding", "C’est pour une inscription, un prix, un campus, ou un dossier étudiant?", "triage before handoff"),
            ResponseVariant("repair", "Compris — je ne vais pas insister. On prépare simplement le transfert vers une personne.", "bot resistance concern"),
        ),
    ),
}


def get_response_family(intent: str) -> ResponseFamily | None:
    return FAMILIES.get(intent)


def choose_variant(intent: str, scope: str = "warm") -> ResponseVariant | None:
    family = get_response_family(intent)
    if not family:
        return None
    for variant in family.variants:
        if variant.scope == scope:
            return variant
    return family.variants[0] if family.variants else None


def choose_scope(*, intent: str, question: str = "", answer: str = "", source_layer: str | None = None) -> str:
    q = (question or "").lower()
    if intent not in {"unsure_start", "too_expensive"} and any(marker in q for marker in ("pas ", "non ", "plutot", "plutôt", "corrige", "je veux dire", "pas practicien", "pas praticien")):
        return "repair"
    if intent in {"too_expensive", "human"}:
        return "reassuring"
    if intent in {"total_n1_n2", "total_all"} and any(marker in q for marker in ("total", "ensemble", "complet", "tout")):
        return "concise"
    if intent in {"price_n2", "price_n3", "weekly", "financing"} and source_layer in DETERMINISTIC_POLISH_SOURCES:
        return "concise"
    if intent == "unsure_start":
        return "warm"
    if intent == "aroma_course" and any(marker in q for marker in ("contenu", "quoi", "quelle", "comment", "info")):
        return "guiding"
    if intent in {"price_n1", "aroma_course"} and source_layer in DETERMINISTIC_POLISH_SOURCES:
        return "concise"
    return "warm"


def render_variant(intent: str, scope: str = "warm", facts: dict[str, Any] | None = None) -> str | None:
    variant = choose_variant(intent, scope)
    if not variant:
        return None
    merged = {**DEFAULT_FACTS, **(facts or {})}
    try:
        return variant.line.format(**merged)
    except KeyError:
        return variant.line


def should_apply_polish(*, intent: str | None, source_layer: str | None, model: str | None, top_score: float = 0) -> bool:
    if intent not in SAFE_POLISH_INTENTS:
        return False
    if source_layer in DETERMINISTIC_POLISH_SOURCES:
        return True
    # For generated/RAG answers, only apply a short service opener to
    # high-confidence orientation/objection intents; keep the grounded facts.
    return bool(intent in {"unsure_start", "too_expensive"} and top_score >= 0.0)


def polish_answer(
    *,
    answer: str,
    intent: str | None,
    question: str,
    source_layer: str | None,
    model: str | None,
    top_score: float,
    facts: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any] | None]:
    if not should_apply_polish(intent=intent, source_layer=source_layer, model=model, top_score=top_score):
        return answer, None
    answer_low = (answer or "").lower()
    # Do not replace grounded aromatherapy content details with a short
    # performance line. The polish family is for openers/confirmations; once the
    # deterministic layer has the actual course contents, preserve them.
    if intent == "aroma_course" and (
        "aromathérapie : les bases" in answer_low
        or "aromatherapie : les bases" in answer_low
        or "huiles essentielles" in answer_low
    ):
        return answer, None
    if intent == "too_expensive" and source_layer in DETERMINISTIC_POLISH_SOURCES and answer.strip():
        return answer, None
    if intent in {"human", "julie"} and source_layer == "local_handoff_layer" and answer.strip():
        return answer, None
    scope = choose_scope(intent=intent or "", question=question, answer=answer, source_layer=source_layer)
    rendered = render_variant(intent or "", scope=scope, facts=facts)
    if not rendered:
        return answer, None
    mode = "replace"
    if source_layer not in DETERMINISTIC_POLISH_SOURCES and answer.strip():
        # Generated/RAG answers keep their grounded details; the family line acts
        # as a controlled service-performance opener.
        mode = "prefix"
        if rendered.lower() not in answer.lower():
            rendered = f"{rendered}\n\n{answer}"
        else:
            rendered = answer
    return rendered, {"intent": intent, "scope": scope, "source_layer": source_layer, "mode": mode}


def family_catalog() -> dict[str, Any]:
    return {
        "scope_count": len(EMOTIONAL_SCOPES),
        "scopes": list(EMOTIONAL_SCOPES),
        "family_count": len(FAMILIES),
        "safe_polish_intents": sorted(SAFE_POLISH_INTENTS),
        "deterministic_sources": sorted(DETERMINISTIC_POLISH_SOURCES),
        "families": [family.to_dict() for family in FAMILIES.values()],
    }


if __name__ == "__main__":
    print(json.dumps(family_catalog(), indent=2, ensure_ascii=False))
