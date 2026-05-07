"""Deterministic AMS handoff/contact answers.

Keeps common human-handoff, callback, info-send, and campus-contact requests
out of the LLM so Scarlett behaves like a reliable receptionist without
pretending she has actually booked, sent, or transferred anything.
"""
import re
import unicodedata

CONTACT_URL = "https://www.academiedemassage.com/contact/"
PHONE = "1 800 475-1964"


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("’", "'")
    return re.sub(r"\s+", " ", text).strip()


def _has_any(q: str, *phrases: str) -> bool:
    return any(p in q for p in phrases)


def _context_summary(context: str) -> str | None:
    c = _norm(context)
    if _has_any(c, "niveau 3", "orthotherapie", "orthothérapie"):
        return "Niveau 3 / orthothérapie"
    if _has_any(c, "niveau 2", "sportif", "anti stress", "anti-stress", "massotherapie avancee", "massothérapie avancée"):
        return "Niveau 2 / spécialisation"
    if _has_any(c, "niveau 1", "praticien en massotherapie", "praticien en massothérapie", "debut", "début"):
        return "Niveau 1 / début de parcours"
    if _has_any(c, "aroma", "aromatherapie", "aromathérapie", "huiles essentielles"):
        return "aromathérapie / cours à la carte"
    if _has_any(c, "campus", "montreal", "montréal", "laval", "quebec", "québec", "brossard", "terrebonne"):
        return "campus / emplacement"
    if _has_any(c, "prix", "cout", "coût", "paiement", "financement", "budget", "cher"):
        return "prix / paiement"
    return None


def _human_answer(context: str = "") -> str:
    topic = _context_summary(context)
    topic_line = f"\n\nJe peux aussi résumer votre demande comme : **{topic}**, pour que la personne comprenne vite le contexte." if topic else ""
    return (
        "Bien sûr. Pour parler à une personne de l’AMS, le plus direct est de passer par le contact officiel.\n\n"
        f"- Téléphone : **{PHONE}**\n"
        f"- Page contact : {CONTACT_URL}"
        f"{topic_line}\n\n"
        "Si vous voulez, je peux vous aider à formuler la demande en une phrase claire avant de l’envoyer."
    )


def _callback_answer(context: str = "") -> str:
    topic = _context_summary(context) or "votre demande AMS"
    return (
        "Oui. Pour demander un rappel ou un rendez-vous, utilisez le contact officiel de l’AMS.\n\n"
        f"- Téléphone : **{PHONE}**\n"
        f"- Page contact : {CONTACT_URL}\n\n"
        f"Message simple à envoyer : « Bonjour, j’aimerais qu’on me rappelle au sujet de **{topic}**. Merci. »\n\n"
        "Je ne vais pas dire que le rappel est réservé tant qu’une personne de l’AMS ne l’a pas confirmé."
    )


def _send_info_answer(context: str = "") -> str:
    topic = _context_summary(context) or "la formation ou le parcours qui vous intéresse"
    return (
        "Oui. Pour recevoir de l’information officielle par écrit, le mieux est de faire la demande via l’AMS.\n\n"
        f"- Page contact : {CONTACT_URL}\n"
        f"- Téléphone : **{PHONE}**\n\n"
        f"Vous pouvez demander : « Pouvez-vous m’envoyer l’information sur **{topic}** ? »\n\n"
        "De mon côté, je peux aussi vous résumer l’essentiel tout de suite si vous voulez comparer avant de contacter l’école."
    )


def _campus_contact_answer(context: str = "") -> str:
    return (
        "Oui. Pour joindre l’AMS au sujet d’un campus précis — adresse, horaire, disponibilités ou dates exactes — passez par le contact officiel.\n\n"
        f"- Téléphone : **{PHONE}**\n"
        f"- Page contact : {CONTACT_URL}\n\n"
        "Mentionnez simplement le campus qui vous intéresse dans votre message. Si vous me dites la ville, je peux aussi vous aider à choisir le campus à nommer."
    )


def _julie_answer(context: str = "") -> str:
    return (
        "Oui — si vous cherchez Julie ou une personne précise de l’AMS, le bon chemin est le contact officiel.\n\n"
        f"- Téléphone : **{PHONE}**\n"
        f"- Page contact : {CONTACT_URL}\n\n"
        "Dans votre message, dites simplement que vous souhaitez joindre Julie ou qu’on vous dirige vers la bonne personne."
    )


def answer_handoff(question: str, conversation_context: str = ""):
    q = _norm(question)

    if not q:
        return None

    asks_julie = "julie" in q
    asks_campus_contact = _has_any(q,
        "contact campus", "joindre le campus", "appeler le campus", "numero du campus", "numéro du campus",
        "telephone du campus", "téléphone du campus", "parler au campus", "contact pour le campus"
    )
    asks_callback = _has_any(q,
        "rappel", "me rappeler", "me rappelle", "qu'on me rappelle", "on me rappelle", "etre rappele", "être rappelé",
        "prendre rendez vous", "prendre rendez-vous", "rendez vous", "rendez-vous", "booker un appel", "planifier un appel",
        "ceduler un appel", "céduler un appel", "appel avec", "par telephone", "par téléphone"
    )
    asks_send_info = _has_any(q,
        "envoyer de l'information", "envoyer des informations", "envoyez moi l'information", "envoie moi l'information",
        "recevoir de l'information", "recevoir les informations", "info par courriel", "information par courriel",
        "envoyer par courriel", "m'envoyer les infos", "m envoyer les infos", "documentation", "brochure"
    )
    asks_human = _has_any(q,
        "parler a quelqu", "parler à quelqu", "parler a une personne", "parler à une personne", "parler avec une personne",
        "agent humain", "un humain", "une personne", "conseiller", "conseillere", "conseillère", "pas un robot",
        "transfere moi", "transfère moi", "mettre avec quelqu", "mettez moi avec", "joindre quelqu", "joindre une personne",
        "contact officiel", "numero de telephone", "numéro de téléphone", "telephone", "téléphone"
    )

    if asks_julie:
        return _julie_answer(conversation_context)
    if asks_campus_contact:
        return _campus_contact_answer(conversation_context)
    if asks_callback:
        return _callback_answer(conversation_context)
    if asks_send_info:
        return _send_info_answer(conversation_context)
    if asks_human:
        return _human_answer(conversation_context)
    return None
