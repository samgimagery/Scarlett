"""Deterministic AMS à-la-carte / continuing education answers."""
import re
import unicodedata

A_LA_CARTE_GROUPS = [
    ("Bases professionnelles", [
        ("Éthique et déontologie professionnelle", "116 $", "8 h"),
        ("Lois et règlements professionnels", "229 $", "24 h"),
        ("Relation d’aide / tenue de dossiers", "739 $", "63 h"),
        ("Anatomie et physiologie intégrées", "1 465 $", "90 h"),
    ]),
    ("Aromathérapie", [
        ("Aromathérapie : les bases", "99 $", ""),
        ("Aromathérapie clinique et scientifique 1", "199 $", "32 h"),
        ("Bases + clinique/scientifique 1", "249 $", "48 h"),
    ]),
    ("Techniques massage / détente", [
        ("Massage aux balles de sel himalayen", "99 $", "8 h"),
        ("Massage aux coquillages chauds", "119 $", ""),
        ("Massage décongestionnant aux bambous", "129 $", "8 h"),
        ("Massage neurosensoriel", "149 $", "7 h"),
        ("Massage bébé/enfant", "205 $", "15 h"),
        ("Massage sportif niveau 1 / Flushmassage", "279 $", "20 h"),
        ("Massage sur chaise", "289 $", "16 h"),
        ("Lomi-Lomi intramusculaire", "299 $", "16 h"),
        ("Massage femme enceinte", "310 $", ""),
        ("Massage Biocorporel", "352 $", "24 h"),
    ]),
    ("Douleur / mobilité / outils", [
        ("Kinésithérapie tissulaire par vacuothérapie", "199 $", "12 h"),
        ("MyoFlossing", "285 $", "8 h"),
        ("Mobilisations myofasciales avec outils", "319 $", "15 h"),
        ("Décongestion tissulaire / thermo-cryo", "349 $", ""),
        ("Décongestion musculaire / trigger points", "399 $", ""),
        ("Mise à niveau kinésithérapie", "429 $", "60 h"),
        ("Dysfonctions organiques", "459 $", ""),
        ("Drainage lymphatique — Dr Leduc", "699 $", "24 h"),
    ]),
    ("Taping / crânio-sacré", [
        ("Taping membres/tronc supérieurs", "450 $", ""),
        ("Taping membres/tronc inférieurs", "450 $", ""),
        ("Taping forfait complet", "799 $", "46 h"),
        ("Thérapie crânio-sacrée intégrée 1", "689 $", "42 h"),
        ("Thérapie crânio-sacrée intégrée 2", "689 $", "42 h"),
        ("Thérapie crânio-sacrée intégrée 3", "689 $", "42 h"),
        ("Thérapie crânio-sacrée intégrée 4", "689 $", "42 h"),
    ]),
]


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("’", "'")
    return re.sub(r"\s+", " ", text).strip()


def answer_continuing_ed(question: str):
    q = _norm(question)
    asks_a_la_carte = any(x in q for x in [
        "a la carte", "à la carte", "formation continue", "formations continues", "cours ponctuel", "cours ponctuels"
    ])
    asks_list = any(x in q for x in ["liste", "quels", "quelles", "autres options", "autre options", "autre cours", "autres cours"])
    if not (asks_a_la_carte and asks_list):
        return None

    lines = [
        "Oui. En plus du parcours principal, AMS offre aussi des **cours à la carte / formations continues** pour compléter une pratique.",
        "",
        "Je vous les regroupe par thème :",
    ]
    for group, courses in A_LA_CARTE_GROUPS:
        lines.append("")
        lines.append(f"**{group}**")
        for title, price, hours in courses:
            details = " · ".join(x for x in [price, hours] if x)
            lines.append(f"- {title}" + (f" — {details}" if details else ""))
    lines.extend([
        "",
        "Ces cours sont surtout des compléments. Le parcours complet reste Niveau 1 → Niveau 2 → Niveau 3 selon l’expérience.",
        "Vous voulez que je vous aide à choisir selon un objectif : douleur/sport, détente/stress, aromathérapie, ou techniques spécialisées ?",
    ])
    return "\n".join(lines)
