"""Deterministic AMS pricing and financing answers.

Keeps common price/financing questions out of the LLM so arithmetic and weekly
amounts stay consistent.
"""
import re
import unicodedata

LEVEL_1_PRICE = 4995
LEVEL_2_PRICE = 7345
LEVEL_3_PRICE = 3595
ADMIN_FEE = 100

LEVEL_1_WEEKLY = 104
LEVEL_2_WEEKLY = 111
LEVEL_3_WEEKLY = 97


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("’", "'")
    return re.sub(r"\s+", " ", text).strip()


def _money(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " $"


def _mentions_price(q: str) -> bool:
    return any(x in q for x in [
        "prix", "combien", "cout", "coute", "tarif", "total", "frais", "payer", "paiement", "financement", "finance", "versement"
    ])


def _mentions_combo(q: str) -> bool:
    compact = q.replace(" ", "")
    return any(x in compact for x in ["1+2", "1+2+3", "niveau1+2", "niveau1+2+3", "niveaux1et2", "niveaux1,2et3"]) or any(
        x in q for x in ["les 3 niveaux", "trois niveaux", "niveau 1 2 3", "niveau 1 et 2", "niveaux 1 et 2"]
    )


def _mentions_financing(q: str) -> bool:
    return any(x in q for x in ["financement", "finance", "paiement", "versement", "semaine", "hebdo", "ifinance", "pret", "prêt", "marge"])


def answer_pricing(question: str):
    q = _norm(question)
    if not _mentions_price(q):
        return None

    wants_combo = _mentions_combo(q) or ("niveau 1" in q and "niveau 2" in q) or "total" in q
    wants_financing = _mentions_financing(q)

    # Let specific non-price content questions go through RAG.
    if not wants_combo and not wants_financing and not any(x in q for x in ["niveau 1", "niveau 2", "niveau 3", "niveaux"]):
        return None

    lines = []
    if wants_combo:
        total_12 = LEVEL_1_PRICE + LEVEL_2_PRICE
        total_123 = total_12 + LEVEL_3_PRICE
        lines.append("Voici les grands totaux du parcours professionnel :")
        lines.append("")
        lines.append(f"- **Niveau 1** : {_money(LEVEL_1_PRICE)}")
        lines.append(f"- **Niveau 1 + Niveau 2** : {_money(total_12)}")
        lines.append(f"- **Niveau 1 + Niveau 2 + Niveau 3** : {_money(total_123)}")
        lines.append("")
        lines.append("Les frais administratifs d’inscription sont de 100 $ pour les programmes professionnels.")
    else:
        if "niveau 3" in q:
            lines.append(f"Le **Niveau 3 | Orthothérapie avancée** est à {_money(LEVEL_3_PRICE)}, ou à partir de {LEVEL_3_WEEKLY} $ / semaine.")
        elif "niveau 2" in q:
            lines.append(f"Le **Niveau 2** est à {_money(LEVEL_2_PRICE)}, ou à partir de {LEVEL_2_WEEKLY} $ / semaine.")
        else:
            lines.append(f"Le **Niveau 1 | Praticien en massothérapie** est à {_money(LEVEL_1_PRICE)}, ou à partir de {LEVEL_1_WEEKLY} $ / semaine.")
        lines.append(f"Les frais administratifs d’inscription sont de {ADMIN_FEE} $.")

    if wants_financing:
        lines.append("")
        lines.append("Pour le paiement, AMS indique :")
        lines.append(f"- Niveau 1 : à partir de {LEVEL_1_WEEKLY} $ / semaine")
        lines.append(f"- Niveau 2 : à partir de {LEVEL_2_WEEKLY} $ / semaine")
        lines.append(f"- Niveau 3 : à partir de {LEVEL_3_WEEKLY} $ / semaine")
        lines.append("- paiement échelonné sans frais ni intérêt possible")
        lines.append("- financement possible via IFINANCE, votre banque ou des marges de crédit partenaires")
        lines.append("")
        lines.append("Les montants hebdomadaires peuvent varier selon l’horaire et la date d’inscription; un conseiller peut confirmer le meilleur plan.")
    else:
        lines.append("")
        lines.append("Je peux aussi vous expliquer les paiements par semaine ou les options de financement si vous voulez comparer le budget.")

    return "\n".join(lines)
