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
        "prix", "combien", "cout", "coute", "tarif", "total", "frais", "payer", "paiement", "financement", "finance", "versement",
        "moyens", "budget", "cher", "chere", "chère", "trop eleve", "trop élevé", "pas capable", "pas les moyens",
        "au dessus de mes moyens", "depasse mon budget", "dépasse mon budget", "budget serre", "budget serré"
    ])


def _mentions_affordability_stress(q: str) -> bool:
    return any(x in q for x in [
        "pas les moyens", "pas de moyens", "j'ai pas les moyens", "jai pas les moyens", "je n'ai pas les moyens",
        "trop cher", "trop chere", "trop chère", "trop eleve", "trop élevé", "c'est cher", "cest cher",
        "pas capable", "budget", "je peux pas payer", "je ne peux pas payer", "au dessus de mes moyens",
        "depasse mon budget", "dépasse mon budget", "budget serre", "budget serré"
    ])


def _mentions_combo(q: str) -> bool:
    compact = q.replace(" ", "")
    return any(x in compact for x in ["1+2", "1+2+3", "niveau1+2", "niveau1+2+3", "niveaux1et2", "niveaux1,2et3"]) or any(
        x in q for x in ["les 3 niveaux", "trois niveaux", "niveau 1 2 3", "niveau 1 et 2", "niveaux 1 et 2"]
    )


def _mentions_financing(q: str) -> bool:
    return any(x in q for x in ["financement", "finance", "paiement", "versement", "semaine", "hebdo", "ifinance", "pret", "prêt", "marge"])


def _payment_already_covered(context: str) -> bool:
    c = _norm(context)
    return any(x in c for x in ["104 semaine", "104 $", "ifinance", "paiement echelonne", "marge de credit", "banque"])


def answer_pricing(question: str, conversation_context: str = ""):
    q = _norm(question)
    if not _mentions_price(q):
        return None

    wants_combo = _mentions_combo(q) or ("niveau 1" in q and "niveau 2" in q) or "total" in q
    wants_financing = _mentions_financing(q)
    affordability_stress = _mentions_affordability_stress(q)

    if affordability_stress:
        if _payment_already_covered(conversation_context):
            return (
                "Je comprends. C’est beaucoup d’argent, et je ne veux pas vous faire tourner en rond.\n\n"
                "Les options de paiement connues ont déjà été couvertes. Si le parcours complet reste trop lourd pour l’instant, AMS a aussi des **cours à la carte / formations continues** avec un engagement plus léger — certains commencent autour de **99 $**.\n\n"
                "Vous préférez que je détaille une option de paiement précise, ou que je vous montre les cours plus courts et moins chers ?"
            )
        return (
            "Je comprends. C’est beaucoup d’argent, et c’est normal de vouloir vérifier si c’est réaliste avant d’avancer.\n\n"
            f"Pour le **Niveau 1**, les options connues sont :\n"
            f"- paiement échelonné à partir de {LEVEL_1_WEEKLY} $ / semaine\n"
            "- financement possible via IFINANCE, votre banque ou une marge de crédit partenaire\n\n"
            "Si vous voulez un engagement plus léger avant le parcours complet, AMS a aussi des **cours à la carte / formations continues** — par exemple aromathérapie, techniques de détente, sport, douleur/mobilité ou spa. Certains commencent autour de **99 $**.\n\n"
            "Vous préférez que je vous montre les options de paiement, ou des cours plus courts et moins chers ?"
        )

    level_markers = [
        "niveau 1", "niveau un", "n1", "premier niveau",
        "niveau 2", "niveau deux", "n2", "deuxieme niveau", "deuxième niveau", "second niveau",
        "niveau 3", "niveau trois", "n3", "troisieme niveau", "troisième niveau", "dernier niveau",
        "niveaux",
    ]

    # Let specific non-price content questions go through RAG.
    if not wants_combo and not wants_financing and not any(x in q for x in level_markers):
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
        asks_n3 = any(x in q for x in ["niveau 3", "niveau trois", "n3", "troisieme niveau", "troisième niveau", "dernier niveau"])
        asks_n2 = any(x in q for x in ["niveau 2", "niveau deux", "n2", "deuxieme niveau", "deuxième niveau", "second niveau"])
        if asks_n3:
            lines.append(f"Le **Niveau 3 | Orthothérapie avancée** est à {_money(LEVEL_3_PRICE)}, ou à partir de {LEVEL_3_WEEKLY} $ / semaine.")
        elif asks_n2:
            lines.append(f"Le **Niveau 2** est à {_money(LEVEL_2_PRICE)}, ou à partir de {LEVEL_2_WEEKLY} $ / semaine.")
        else:
            lines.append(f"Le **Niveau 1 | Praticien en massothérapie** est à {_money(LEVEL_1_PRICE)}, ou à partir de {LEVEL_1_WEEKLY} $ / semaine.")
        lines.append(f"Les frais administratifs d’inscription sont de {ADMIN_FEE} $.")

    if wants_financing:
        lines.append("")
        lines.append("Pour le paiement, les options connues sont :")
        if any(x in q for x in ["niveau 2", "niveau deux", "n2", "deuxieme niveau", "deuxième niveau"]) and "niveau 1" not in q:
            lines.append(f"- paiement échelonné à partir de {LEVEL_2_WEEKLY} $ / semaine")
        elif any(x in q for x in ["niveau 3", "niveau trois", "n3", "troisieme niveau", "troisième niveau"]) and "niveau 1" not in q:
            lines.append(f"- paiement échelonné à partir de {LEVEL_3_WEEKLY} $ / semaine")
        else:
            lines.append(f"- paiement échelonné à partir de {LEVEL_1_WEEKLY} $ / semaine")
        lines.append("- financement possible via IFINANCE, votre banque ou une marge de crédit partenaire")
        lines.append("")
        lines.append("Je peux détailler une de ces options si vous me le demandez.")
    else:
        lines.append("")
        lines.append("Si vous voulez, je peux aussi vous donner les options de paiement.")

    return "\n".join(lines)
