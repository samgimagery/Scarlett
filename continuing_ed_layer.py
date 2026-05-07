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


def _sport_bundle_answer():
    return (
        "Oui — si votre intérêt est le **sport**, je regarderais d’abord les options liées au mouvement, à la récupération et aux douleurs musculaires.\n\n"
        "**Cours à la carte pertinents**\n"
        "- **Massage sportif niveau 1 / Flushmassage** — 279 $ · 20 h\n"
        "- **MyoFlossing** — 285 $ · 8 h\n"
        "- **Mobilisations myofasciales avec outils** — 319 $ · 15 h\n"
        "- **Décongestion musculaire / trigger points** — 399 $\n"
        "- **Taping membres/tronc supérieurs** — 450 $\n"
        "- **Taping membres/tronc inférieurs** — 450 $\n"
        "- **Kinésithérapie tissulaire par vacuothérapie** — 199 $ · 12 h\n\n"
        "Si vous voulez un parcours plus complet qu’un atelier, la voie principale à regarder ensuite est le **Niveau 2 | Masso-kinésithérapie spécialisation en sportif**."
    )


def _stress_bundle_answer():
    return (
        "Oui — pour un axe **stress / détente**, je viserais surtout les cours qui développent le toucher relaxant, l’accompagnement et les approches plus douces.\n\n"
        "**Cours à la carte pertinents**\n"
        "- **Massage neurosensoriel** — 149 $ · 7 h\n"
        "- **Massage aux balles de sel himalayen** — 99 $ · 8 h\n"
        "- **Massage aux coquillages chauds** — 119 $\n"
        "- **Massage Biocorporel** — 352 $ · 24 h\n"
        "- **Lomi-Lomi intramusculaire** — 299 $ · 16 h\n"
        "- **Relation d’aide / tenue de dossiers** — 739 $ · 63 h\n\n"
        "Si vous voulez en faire un vrai parcours professionnel, la voie complète à regarder ensuite est le **Niveau 2 | Massothérapie avancée spécialisation anti-stress**."
    )


def _pain_mobility_bundle_answer():
    return (
        "Oui — pour un axe **douleur / mobilité**, je regarderais les cours à la carte qui touchent aux tissus, aux outils thérapeutiques et au mouvement.\n\n"
        "**Cours à la carte pertinents**\n"
        "- **Décongestion musculaire / trigger points** — 399 $\n"
        "- **Décongestion tissulaire / thermo-cryo** — 349 $\n"
        "- **Mobilisations myofasciales avec outils** — 319 $ · 15 h\n"
        "- **MyoFlossing** — 285 $ · 8 h\n"
        "- **Kinésithérapie tissulaire par vacuothérapie** — 199 $ · 12 h\n"
        "- **Mise à niveau kinésithérapie** — 429 $ · 60 h\n"
        "- **Drainage lymphatique — Dr Leduc** — 699 $ · 24 h\n\n"
        "Pour une formation plus structurée, ce thème rejoint aussi le **Niveau 2 sportif** et le **Niveau 3 | Orthothérapie avancée**."
    )


def _aromatherapy_bundle_answer():
    return (
        "Oui — pour un axe **aromathérapie**, AMS a des options à la carte assez directes.\n\n"
        "**Cours à la carte pertinents**\n"
        "- **Aromathérapie : les bases** — 99 $\n"
        "- **Aromathérapie clinique et scientifique 1** — 199 $ · 32 h\n"
        "- **Bases + clinique/scientifique 1** — 249 $ · 48 h\n\n"
        "C’est un bon complément si vous voulez enrichir une pratique de massage détente, spa ou accompagnement bien-être."
    )


def _aromatherapy_content_answer():
    return (
        "Pour l’**aromathérapie**, l’idée est d’apprendre à utiliser les huiles essentielles de façon sécuritaire et utile dans une pratique de massage ou de bien-être.\n\n"
        "**Aromathérapie : les bases** — 99 $\n"
        "- notions de base sur les huiles essentielles\n"
        "- précautions d’usage et sécurité\n"
        "- choix des huiles selon l’objectif\n"
        "- intégration simple avec une pratique de détente ou de massage\n\n"
        "**Aromathérapie clinique et scientifique 1** — 199 $ · 32 h\n"
        "- approche plus approfondie et structurée\n"
        "- usages cliniques/scientifiques de base\n"
        "- choix plus précis selon les besoins\n\n"
        "**Forfait bases + clinique/scientifique 1** — 249 $ · 48 h\n\n"
        "Si vous voulez seulement explorer sans gros engagement, je commencerais par **Aromathérapie : les bases**."
    )


def _pregnancy_family_bundle_answer():
    return (
        "Oui — pour un axe **grossesse / bébé / famille**, je regarderais surtout les cours qui touchent au soin doux et à l’accompagnement.\n\n"
        "**Cours à la carte pertinents**\n"
        "- **Massage femme enceinte** — 310 $\n"
        "- **Massage bébé/enfant** — 205 $ · 15 h\n"
        "- **Relation d’aide / tenue de dossiers** — 739 $ · 63 h\n"
        "- **Aromathérapie : les bases** — 99 $\n\n"
        "Si votre objectif est de bâtir une pratique complète, ces cours servent surtout de compléments au parcours principal de massothérapie."
    )


def _spa_relaxation_bundle_answer():
    return (
        "Oui — pour viser un contexte **spa / relaxation**, je choisirais des cours qui donnent des techniques agréables, différenciantes et faciles à intégrer en service.\n\n"
        "**Cours à la carte pertinents**\n"
        "- **Massage aux balles de sel himalayen** — 99 $ · 8 h\n"
        "- **Massage aux coquillages chauds** — 119 $\n"
        "- **Massage neurosensoriel** — 149 $ · 7 h\n"
        "- **Lomi-Lomi intramusculaire** — 299 $ · 16 h\n"
        "- **Massage Biocorporel** — 352 $ · 24 h\n"
        "- **Aromathérapie : les bases** — 99 $\n\n"
        "Pour une base professionnelle complète, le point de départ reste le **Niveau 1 | Praticien en massothérapie**."
    )


def _try_light_commitment_answer():
    return (
        "Oui — si vous voulez **essayer sans vous engager tout de suite** dans un long parcours, je regarderais les cours à la carte les plus légers.\n\n"
        "**Bons points d’entrée**\n"
        "- **Aromathérapie : les bases** — 99 $\n"
        "- **Massage aux balles de sel himalayen** — 99 $ · 8 h\n"
        "- **Massage aux coquillages chauds** — 119 $\n"
        "- **Massage neurosensoriel** — 149 $ · 7 h\n"
        "- **Aromathérapie clinique et scientifique 1** — 199 $ · 32 h\n"
        "- **Massage bébé/enfant** — 205 $ · 15 h\n\n"
        "C’est utile pour tester un intérêt ou ajouter une technique précise. Si votre objectif est de devenir massothérapeute, le parcours complet commence ensuite au **Niveau 1**."
    )


def _career_practice_bundle_answer():
    return (
        "Oui — si votre objectif est de **travailler en clinique, spa, ou ouvrir votre pratique**, je regarderais d’abord la base professionnelle, puis les compléments selon votre clientèle.\n\n"
        "**Base utile**\n"
        "- **Niveau 1 | Praticien en massothérapie** — parcours principal pour débuter\n"
        "- **Éthique et déontologie professionnelle** — 116 $ · 8 h\n"
        "- **Lois et règlements professionnels** — 229 $ · 24 h\n"
        "- **Relation d’aide / tenue de dossiers** — 739 $ · 63 h\n"
        "- **Anatomie et physiologie intégrées** — 1 465 $ · 90 h\n\n"
        "Ensuite, vous pouvez spécialiser votre offre : sport, douleur/mobilité, détente/spa, grossesse/bébé ou aromathérapie."
    )


def answer_continuing_ed(question: str):
    q = _norm(question)

    if "drainage" in q and "lymph" in q:
        return (
            "Oui. L’AMS offre **Drainage lymphatique — méthode du Dr Leduc**.\n\n"
            "Repères : **699 $**, environ **24 h**.\n\n"
            "C’est une formation continue spécialisée. Je peux aussi vous situer les autres cours douleur/mobilité si vous comparez."
        )

    sport_interest = any(x in q for x in [
        "massage sportif", "sportif", "sport", "athlete", "athlète", "athletes", "athlètes",
        "recuperation sportive", "récupération sportive", "performance", "entrainement", "entraînement"
    ])
    if sport_interest:
        return _sport_bundle_answer()

    asks_content = any(x in q for x in [
        "contenu", "dans le cours", "du cours", "apprend", "apprendre", "objectif", "objectifs", "matiere", "matière"
    ])
    mentions_aromatherapy = "aroma" in q or "aromatherapie" in q or "aromathérapie" in q or "laromatherapie" in q or "laromathérapie" in q
    asks_aromatherapy_course_content = mentions_aromatherapy and asks_content and any(x in q for x in [
        "cours d'aromatherapie", "cours d aromatherapie", "cours aromatherapie",
        "aromatherapie a la carte", "aromathérapie à la carte", "aromatherapie : les bases",
        "aromatherapie clinique", "clinique/scientifique",
    ])
    asks_niveau_1_content = ("niveau 1" in q or "praticien en massotherapie" in q or "praticien en massothérapie" in q) and asks_content and not asks_aromatherapy_course_content

    if mentions_aromatherapy and asks_aromatherapy_course_content:
        return _aromatherapy_content_answer()
    if mentions_aromatherapy and not asks_niveau_1_content:
        return _aromatherapy_bundle_answer()

    family_interest = any(x in q for x in [
        "grossesse", "enceinte", "femme enceinte", "bébé", "bebe", "enfant", "enfants", "famille", "familial"
    ])
    if family_interest:
        return _pregnancy_family_bundle_answer()

    spa_interest = any(x in q for x in [
        "spa", "hotel", "hôtel", "salon", "massages relaxants", "soins relaxants"
    ])
    if spa_interest:
        return _spa_relaxation_bundle_answer()

    pain_mobility_interest = any(x in q for x in [
        "douleur", "douleurs", "mobilite", "mobilité", "mouvement", "trigger", "myofascial", "myofasciale",
        "kinesitherapie", "kinésithérapie", "orthotherapie", "orthothérapie", "decongestion", "décongestion",
        "tension", "tensions", "musculaire", "musculaires", "therapeutique", "thérapeutique"
    ])
    if pain_mobility_interest:
        return _pain_mobility_bundle_answer()

    stress_interest = any(x in q for x in [
        "stress", "anti stress", "anti-stress", "detente", "détente", "relaxation", "relaxant",
        "anxiete", "anxiété", "calme", "bien etre", "bien-être"
    ])
    if stress_interest:
        return _stress_bundle_answer()

    career_interest = any(x in q for x in [
        "carriere", "carrière", "emploi", "travailler", "travail", "clinique", "ouvrir", "pratique",
        "cabinet", "a mon compte", "à mon compte", "professionnel", "professionnelle"
    ])
    if career_interest:
        return _career_practice_bundle_answer()

    asks_a_la_carte = any(x in q for x in [
        "a la carte", "à la carte", "formation continue", "formations continues", "cours ponctuel", "cours ponctuels"
    ])
    asks_light_commitment = any(x in q for x in [
        "juste essayer", "simplement essayer", "essayer avant", "tester avant", "tester sans", "petit cours",
        "cours court", "cours courts", "formation courte", "formations courtes", "atelier", "ateliers",
        "pas m engager", "pas m'engager", "sans m engager", "sans m'engager", "engagement plus leger", "engagement plus léger",
        "petit engagement", "moins long", "moins longtemps"
    ])
    asks_list = any(x in q for x in ["liste", "quels", "quelles", "autres options", "autre options", "autre cours", "autres cours", "cours moins", "moins cher", "moins chers", "plus economique", "plus économique", "programmes", "offrez"])
    lower_cost = any(x in q for x in ["moins cher", "moins chers", "plus economique", "plus économique", "abordable", "abordables", "au dessus de mes moyens", "budget"])
    programme_overview = any(x in q for x in ["quels programmes", "programmes offrez", "quelles formations", "formations offrez", "cours offrez"])
    if asks_light_commitment and not lower_cost and not asks_a_la_carte:
        return _try_light_commitment_answer()
    if not ((asks_a_la_carte and asks_list) or lower_cost or programme_overview or asks_light_commitment):
        return None

    if programme_overview and not lower_cost and not asks_a_la_carte:
        return (
            "Oui. À l’AMS, je regrouperais l’offre en trois grandes familles.\n\n"
            "- **Parcours principal en massothérapie** — Niveau 1 pour commencer, puis Niveau 2 et Niveau 3 selon l’expérience et l’objectif.\n"
            "- **Spécialisations / perfectionnement** — sport, douleur/mobilité, détente, spa, grossesse/famille, aromathérapie.\n"
            "- **Cours à la carte** — des formations plus courtes si vous voulez explorer ou compléter une pratique sans vous engager tout de suite dans le parcours complet.\n\n"
            "Si vous me dites si vous débutez ou si vous avez déjà une formation, je peux vous orienter vers le bon point de départ."
        )

    lines = [
        "Oui. En plus du parcours principal, AMS offre aussi des **cours à la carte / formations continues** pour compléter une pratique ou explorer une option plus abordable.",
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
