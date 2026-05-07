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
    "greeting",
    "greeting_allo",
    "how_are_you",
    "what_can_help",
    "aroma_course",
    "continuing_ed_list",
    "sport_course",
    "specific_course",
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
    "julie",
    "didnt_hear",
    "repeat",
    "unclear",
    "signup_link",
    "signup_direct",
    "reserve_place",
}

DETERMINISTIC_POLISH_SOURCES = {
    "local_identity_layer",
    "local_service_confidence_layer",
    "local_pricing_layer",
    "local_continuing_ed_layer",
    "local_service_tile_layer",
    "local_handoff_layer",
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
    "greeting": ResponseFamily(
        intent="greeting",
        fact_slots=("name", "scope"),
        notes="Opening moment. Keep short, calm, and receptionist-like.",
        variants=(
            ResponseVariant("concise", "Bonjour, je suis Scarlett.", "pure greeting"),
            ResponseVariant("warm", "Bonjour, je suis Scarlett. Je peux vous aider avec les formations, les prix, les campus ou l’inscription à l’AMS.", "opening with scope"),
            ResponseVariant("reassuring", "Bonjour, je suis Scarlett. On va y aller simplement.", "hesitant caller"),
            ResponseVariant("guiding", "Bonjour, je suis Scarlett. Vous cherchez une formation, un prix, un campus ou une inscription?", "orient caller"),
            ResponseVariant("repair", "Je reprends simplement: je suis Scarlett, la réception virtuelle de l’AMS.", "identity confusion"),
        ),
    ),
    "greeting_allo": ResponseFamily(
        intent="greeting_allo",
        fact_slots=("name", "scope"),
        variants=(
            ResponseVariant("concise", "Allô, je suis Scarlett.", "phone-style greeting"),
            ResponseVariant("warm", "Allô, je suis Scarlett. Je peux vous aider avec les formations, les prix, les campus ou l’inscription à l’AMS.", "phone-style opening with scope"),
            ResponseVariant("reassuring", "Allô, je suis Scarlett. On va y aller simplement.", "hesitant caller"),
            ResponseVariant("guiding", "Allô, je suis Scarlett. Vous cherchez une formation, un prix, un campus ou une inscription?", "orient caller"),
            ResponseVariant("repair", "Je reprends simplement: je suis Scarlett, la réception virtuelle de l’AMS.", "identity confusion"),
        ),
    ),
    "how_are_you": ResponseFamily(
        intent="how_are_you",
        fact_slots=("scope",),
        variants=(
            ResponseVariant("concise", "Oui, ça va très bien, merci.", "social check-in"),
            ResponseVariant("warm", "Ça va très bien, merci. Quelle information AMS souhaitez-vous vérifier?", "social check-in then orient"),
            ResponseVariant("reassuring", "Ça va très bien, merci. Prenons ça simplement.", "hesitant caller"),
            ResponseVariant("guiding", "Ça va très bien, merci. Vous voulez parler formation, prix, campus ou inscription?", "orient caller"),
            ResponseVariant("repair", "Oui, ça va très bien. Je reviens à votre question AMS.", "redirect"),
        ),
    ),
    "what_can_help": ResponseFamily(
        intent="what_can_help",
        fact_slots=("scope",),
        variants=(
            ResponseVariant("concise", "Je peux vous aider avec les formations, les prix, les campus, l’inscription et le bon parcours.", "capability scope"),
            ResponseVariant("warm", "Je peux vous aider à comparer les formations, comprendre les prix, choisir un campus ou préparer l’inscription.", "help menu"),
            ResponseVariant("reassuring", "Je peux vous orienter étape par étape: formation, prix, campus, inscription, ou prochain bon choix.", "hesitant caller"),
            ResponseVariant("guiding", "Dites-moi simplement si vous voulez parler formation, prix, campus ou inscription, et je vous guide.", "menu prompt"),
            ResponseVariant("repair", "Je précise: je réponds aux questions pratiques sur l’AMS — formations, prix, campus et inscription.", "scope correction"),
        ),
    ),
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
    "continuing_ed_list": ResponseFamily(
        intent="continuing_ed_list",
        fact_slots=("theme", "lowest_price", "next_step"),
        notes="Continuing-ed/course browsing opener. Always preserve grounded local_continuing_ed_layer lists as the body.",
        variants=(
            ResponseVariant("concise", "Oui — je peux vous orienter dans les cours à la carte sans mélanger ça avec le parcours complet.", "course browsing"),
            ResponseVariant("warm", "Oui, bien sûr. Je vous regroupe les options à la carte par thème pour que ce soit plus facile à comparer.", "list or broad browsing"),
            ResponseVariant("reassuring", "Oui — si le parcours complet semble trop lourd, on peut regarder les options plus courtes et plus abordables d’abord.", "lower-cost or try-first browsing"),
            ResponseVariant("guiding", "Je peux vous guider par objectif: essayer d’abord, détente/spa, sport, douleur/mobilité, aromathérapie, ou pratique professionnelle.", "theme choice"),
            ResponseVariant("repair", "Vous avez raison — on reste sur les cours à la carte, pas sur le parcours complet. Je reprends avec les options pertinentes.", "course/path confusion"),
        ),
    ),
    "sport_course": ResponseFamily(
        intent="sport_course",
        fact_slots=("theme", "next_step"),
        notes="Sport continuing-ed opener. Preserve concrete course list from local layer.",
        variants=(
            ResponseVariant("concise", "Oui — pour le sport, je regarde surtout récupération, mobilité et douleurs musculaires.", "sport interest"),
            ResponseVariant("warm", "Oui, bien sûr. Pour un axe sportif, je vous regroupe les cours utiles autour du mouvement et de la récupération.", "normal sport browsing"),
            ResponseVariant("reassuring", "Oui — on peut commencer par des cours ciblés avant de parler d’un parcours sportif plus complet.", "hesitant sport caller"),
            ResponseVariant("guiding", "Vous cherchez plutôt performance sportive, douleur musculaire, taping, ou récupération?", "sport theme choice"),
            ResponseVariant("repair", "Je reprends sur le sport précisément, pas sur tous les cours à la carte.", "correction"),
        ),
    ),
    "specific_course": ResponseFamily(
        intent="specific_course",
        fact_slots=("course_name", "price", "duration"),
        notes="Specific à-la-carte course opener. Preserve the exact deterministic course fact body.",
        variants=(
            ResponseVariant("concise", "Oui — je vous donne le repère précis pour ce cours.", "specific course lookup"),
            ResponseVariant("warm", "Oui, je vous le situe simplement avec le prix et la durée connus.", "normal lookup"),
            ResponseVariant("reassuring", "Oui — on reste sur ce cours précis, sans vous noyer dans tout le catalogue.", "caller wants narrow answer"),
            ResponseVariant("guiding", "Je peux aussi vous montrer les cours voisins si vous comparez dans le même thème.", "next comparison"),
            ResponseVariant("repair", "Je reprends sur ce cours-là seulement.", "correction"),
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
            ResponseVariant("concise", "Bien sûr — je peux vous orienter vers une personne de l’AMS sans prétendre transférer l’appel moi-même.", "generic human handoff"),
            ResponseVariant("warm", "Oui, bien sûr. Je peux préparer le bon contexte pour que votre demande soit claire quand vous contactez l’AMS.", "cooperative handoff"),
            ResponseVariant("reassuring", "Aucun problème — je vous donne le chemin officiel, sans prétendre qu’un rappel ou un transfert est déjà confirmé.", "callback or transfer safety"),
            ResponseVariant("guiding", "Je peux vous aider à formuler la demande: inscription, prix, campus, dossier étudiant, ou rappel.", "handoff triage"),
            ResponseVariant("repair", "Compris — je ne vais pas insister. Je vous oriente simplement vers le contact officiel de l’AMS.", "bot resistance concern"),
        ),
    ),
    "julie": ResponseFamily(
        intent="julie",
        fact_slots=("person", "official_contact_path"),
        notes="Julie/person-specific handoff. Never claim Scarlett transferred the caller or contacted Julie.",
        variants=(
            ResponseVariant("concise", "Oui — je peux vous orienter vers le bon contact pour joindre Julie, sans prétendre la transférer directement.", "Julie request"),
            ResponseVariant("warm", "Bien sûr. Si vous cherchez Julie, je vous aide à formuler la demande proprement pour l’AMS.", "cooperative Julie handoff"),
            ResponseVariant("reassuring", "Aucun souci — je vous donne le chemin officiel pour demander Julie ou la bonne personne, sans inventer un transfert.", "transfer safety"),
            ResponseVariant("guiding", "Dans le message, indiquez simplement que vous souhaitez joindre Julie ou être dirigé vers la bonne personne.", "what to say"),
            ResponseVariant("repair", "Je précise: je peux vous aider à demander Julie, mais je ne peux pas la joindre ou confirmer un transfert moi-même.", "fake-transfer correction"),
        ),
    ),
    "didnt_hear": ResponseFamily(
        intent="didnt_hear",
        fact_slots=("previous_answer",),
        notes="Voice/ASR repair. Keep short, interruptible, and local; never call RAG just to recover audio.",
        variants=(
            ResponseVariant("concise", "Pas de problème — je le reformule plus simplement.", "caller did not hear or understand"),
            ResponseVariant("warm", "Bien sûr. Je vais le reprendre plus clairement, en une phrase.", "gentle repair"),
            ResponseVariant("reassuring", "Aucun souci — ça arrive. Je reprends calmement.", "audio or ASR friction"),
            ResponseVariant("guiding", "Je peux reprendre la dernière réponse, ou préciser seulement la partie qui n’était pas claire.", "offer repair branch"),
            ResponseVariant("repair", "Je reprends depuis le début, plus simplement.", "explicit repair request"),
        ),
    ),
    "repeat": ResponseFamily(
        intent="repeat",
        fact_slots=("previous_answer",),
        notes="Repeat request. Do not add new facts; signal a clean repeat.",
        variants=(
            ResponseVariant("concise", "D’accord. Je vous le redis simplement.", "direct repeat"),
            ResponseVariant("warm", "Oui, bien sûr. Je reprends la dernière réponse plus tranquillement.", "gentle repeat"),
            ResponseVariant("reassuring", "Aucun problème — je peux répéter sans aller plus vite.", "caller missed it"),
            ResponseVariant("guiding", "Je peux répéter tout, ou seulement le prix, le programme, ou la prochaine étape.", "branch repeat"),
            ResponseVariant("repair", "Je reprends, plus court et plus clair.", "repeat after confusion"),
        ),
    ),
    "unclear": ResponseFamily(
        intent="unclear",
        fact_slots=("clarification_target",),
        notes="Clarification request. Ask a tiny targeted question; do not over-explain.",
        variants=(
            ResponseVariant("concise", "Pas de souci — quelle partie voulez-vous que je précise?", "direct clarification"),
            ResponseVariant("warm", "Bien sûr. Dites-moi juste la partie floue, et je la reprends clairement.", "caller confused"),
            ResponseVariant("reassuring", "Aucun souci — on peut y aller plus simplement.", "overwhelmed caller"),
            ResponseVariant("guiding", "C’est le prix, le choix du programme, le campus, ou l’inscription qui n’est pas clair?", "targeted clarification"),
            ResponseVariant("repair", "Je simplifie: dites-moi le point qui bloque, et je reprends à partir de là.", "confusion repair"),
        ),
    ),
    "signup_link": ResponseFamily(
        intent="signup_link",
        fact_slots=("official_signup_path", "programme_context"),
        notes="Action request. Guide to the official AMS signup path; never imply Scarlett sent a link or submitted anything.",
        variants=(
            ResponseVariant("concise", "Oui — je peux vous guider vers le bon lien d’inscription officiel, sans rien soumettre à votre place.", "direct link request"),
            ResponseVariant("warm", "Bien sûr. Je vais vous orienter vers le lien officiel, et vous gardez le contrôle de l’inscription.", "normal action request"),
            ResponseVariant("reassuring", "Oui — on peut avancer prudemment. Je vous indique le bon endroit officiel, sans confirmer d’inscription pour vous.", "caller ready but needs safety"),
            ResponseVariant("guiding", "Avant le lien, je veux juste confirmer: c’est pour le Niveau 1, un autre niveau, ou un cours à la carte?", "needs programme context"),
            ResponseVariant("repair", "Je précise: je peux vous diriger vers le lien officiel, mais je ne peux pas envoyer ou remplir le formulaire à votre place.", "fake-action correction"),
        ),
    ),
    "signup_direct": ResponseFamily(
        intent="signup_direct",
        fact_slots=("programme_context", "official_next_step"),
        notes="Direct signup intent. Be useful but honest: no fake registration, no fake booking.",
        variants=(
            ResponseVariant("concise", "Parfait — je peux vous guider vers la bonne étape d’inscription officielle, mais je ne peux pas vous inscrire automatiquement.", "ready to sign up"),
            ResponseVariant("warm", "Très bien. On va le faire proprement: je confirme d’abord le bon parcours, puis je vous dirige vers l’étape officielle.", "normal signup"),
            ResponseVariant("reassuring", "Oui — et je veux éviter de vous envoyer au mauvais endroit. Je confirme le parcours avant l’inscription.", "caller needs guidance"),
            ResponseVariant("guiding", "C’est pour le Niveau 1, un autre niveau, ou un cours à la carte?", "needs programme context"),
            ResponseVariant("repair", "Je précise: je peux vous guider vers l’inscription, mais je ne peux pas la compléter ou la confirmer à votre place.", "fake-action correction"),
        ),
    ),
    "reserve_place": ResponseFamily(
        intent="reserve_place",
        fact_slots=("programme_context", "official_reservation_path"),
        notes="Reservation intent. Never claim a seat is held; guide to official contact/signup path.",
        variants=(
            ResponseVariant("concise", "Je peux vous guider vers la bonne étape pour réserver officiellement, mais je ne peux pas bloquer une place moi-même.", "reserve ask"),
            ResponseVariant("warm", "Parfait. Je peux vous aider à choisir le bon chemin officiel pour demander une place, sans prétendre qu’elle est déjà réservée.", "normal reserve ask"),
            ResponseVariant("reassuring", "Oui — je peux vous guider, mais la place doit être confirmée par l’AMS.", "avoid false confirmation"),
            ResponseVariant("guiding", "Pour quelle formation voulez-vous réserver: Niveau 1, Niveau 2, Niveau 3, ou un cours à la carte?", "needs programme context"),
            ResponseVariant("repair", "Je reprends clairement: je peux orienter la demande de réservation, mais je ne peux pas réserver la place à votre place.", "fake-reservation correction"),
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
    if intent in {"greeting", "greeting_allo"}:
        return "concise" if (question or "").strip().lower().rstrip("?!.,") in {"bonjour", "salut", "allo", "allô"} else "warm"
    if intent == "how_are_you":
        return "warm"
    if intent == "what_can_help":
        return "concise"
    if intent in {"didnt_hear", "repeat"}:
        return "concise"
    if intent == "unclear":
        return "guiding" if any(marker in q for marker in ("quoi", "hein", "pas clair", "comprends pas", "comprend pas")) else "concise"
    if intent in {"signup_link", "signup_direct", "reserve_place"}:
        if any(marker in q for marker in ("lien", "formulaire", "page")):
            return "concise"
        if any(marker in q for marker in ("reserve", "réserve", "place", "siege", "siège", "spot")):
            return "reassuring" if intent == "reserve_place" else "guiding"
        return "guiding"
    if intent not in {"unsure_start", "too_expensive"} and any(marker in q for marker in ("pas ", "non ", "plutot", "plutôt", "corrige", "je veux dire", "pas practicien", "pas praticien")):
        return "repair"
    if intent == "julie":
        return "concise" if "julie" in q else "reassuring"
    if intent == "human":
        if any(marker in q for marker in ("rappel", "rappeler", "rendez", "appel", "booker", "ceduler", "céduler")):
            return "reassuring"
        if any(marker in q for marker in ("courriel", "email", "information", "documentation", "brochure", "campus")):
            return "warm"
        return "concise"
    if intent == "continuing_ed_list":
        if any(marker in q for marker in ("moins cher", "moins chers", "abordable", "budget", "trop cher", "juste essayer", "formation courte", "cours court", "atelier", "sans m engager", "sans m'engager")):
            return "reassuring"
        if any(marker in q for marker in ("quel", "quels", "liste", "options", "offrez", "programme")):
            return "warm"
        return "guiding"
    if intent == "sport_course":
        return "concise" if any(marker in q for marker in ("sport", "sportif", "massage sportif")) else "warm"
    if intent == "specific_course":
        return "concise"
    if intent == "too_expensive":
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
    if source_layer == "local_continuing_ed_layer" and intent not in {"aroma_course", "continuing_ed_list", "sport_course", "specific_course"}:
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
    if source_layer in DETERMINISTIC_POLISH_SOURCES and source_layer != "local_handoff_layer" and answer.strip() and (
        "1 800 475-1964" in answer or "academiedemassage.com/contact" in answer
    ):
        return answer, None
    scope = choose_scope(intent=intent or "", question=question, answer=answer, source_layer=source_layer)
    rendered = render_variant(intent or "", scope=scope, facts=facts)
    if not rendered:
        return answer, None
    mode = "replace"
    if (source_layer not in DETERMINISTIC_POLISH_SOURCES or source_layer in {"local_handoff_layer", "local_continuing_ed_layer"}) and answer.strip():
        # Generated/RAG, handoff, and continuing-ed answers keep their grounded
        # details; the family line acts as a controlled service-performance opener.
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
