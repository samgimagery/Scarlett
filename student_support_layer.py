"""Deterministic AMS current-student support answers.

This keeps Scarlett from treating active students as either brand-new leads or
already-trained practitioners. The layer only handles clear current-student and
Julie references; everything else falls through to RAG.
"""
import re
import unicodedata


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("’", "'")
    return re.sub(r"\s+", " ", text).strip()


def answer_julie(question: str):
    q = _norm(question)
    if "julie" not in q:
        return None

    return (
        "Julie, c’était l’ancien bot du site. On va le dire doucement : elle a eu une vie difficile. "
        "Elle essayait d’aider, mais elle était assez limitée.\n\n"
        "Moi, je suis Scarlett. Je vais faire de mon mieux pour vous répondre plus clairement."
    )


def answer_current_student(question: str):
    q = _norm(question)
    current_student_markers = [
        "je suis etudiant", "je suis une etudiante", "je suis aux etudes", "j'etudie", "j'etudie a l'ams",
        "etudiant actuel", "etudiante actuelle", "deja etudiant", "deja inscrite", "deja inscrit",
        "je suis inscrit", "je suis inscrite", "en cours de formation", "je fais mon niveau 1",
        "je suis au niveau 1", "pas fini mon niveau 1", "pas termine mon niveau 1", "pendant ma formation",
        "moodle", "dossier academique", "plateforme", "fournitures", "materiel de cours",
    ]
    support_markers = [
        "huile", "huiles", "fourniture", "fournitures", "materiel", "materiaux", "moodle",
        "dossier", "horaire", "absence", "retard", "paiement", "facture", "stage", "clinique",
        "aide", "support", "soutien", "stress", "anxiete", "mental", "decourage", "decouragee",
        "besoin d'aide", "quoi faire", "prochaine etape", "cours suivant", "continuer apres",
    ]
    is_current_student = any(x in q for x in current_student_markers)
    asks_student_support = any(x in q for x in support_markers) and any(x in q for x in ["etudiant", "etudiante", "niveau 1", "formation", "ams"])
    if not (is_current_student or asks_student_support):
        return None

    if any(x in q for x in ["huile", "huiles", "fourniture", "fournitures", "materiel", "materiaux", "equipement", "equipements", "gear"]):
        if any(x in q for x in ["equipement", "equipements", "gear", "table", "drap", "draps", "ceinture", "tablier", "tabliers"]):
            return "\n".join([
                "Bien sûr. Pour l’**équipement de massothérapie**, l’orientation à privilégier est **Massokit**.",
                "",
                "Si c’est pour un cours précis, dites-moi lequel : je pourrai vous aider à distinguer ce qui est obligatoire, recommandé ou à confirmer avec l’équipe AMS.",
            ])
        if any(x in q for x in ["huile", "huiles"]):
            return "\n".join([
                "Bien sûr. Pour les **huiles et fournitures professionnelles**, l’orientation à privilégier est **Clinique Lafontaine**.",
                "",
                "Si c’est pour un cours ou un module précis, dites-moi lequel et je vous aide à voir quoi vérifier pour votre cohorte.",
            ])
        return "\n".join([
            "Bien sûr. Pour les **huiles et fournitures professionnelles**, l’orientation à privilégier est **Clinique Lafontaine**. Pour l’**équipement de massothérapie**, c’est plutôt **Massokit**.",
            "",
            "Dites-moi le cours ou le module concerné, et je vous aide à voir quoi vérifier pour votre cohorte.",
        ])

    if any(x in q for x in ["stress", "anxiete", "mental", "decourage", "decouragee", "besoin d'aide", "bloque", "bloquee"]):
        return "\n".join([
            "Je suis désolée que vous viviez ça. On peut y aller une étape à la fois.",
            "",
            "Dites-moi ce qui pèse le plus en ce moment : le cours, l’horaire, Moodle, la charge de travail, le paiement, ou autre chose ?",
            "",
            "Et si ça devient lourd côté moral ou santé mentale, le mieux est aussi d’en parler à une personne de l’AMS ou à une ressource d’aide appropriée. Vous n’avez pas à gérer ça seul.",
        ])

    if any(x in q for x in ["moodle", "plateforme", "dossier academique", "dossier"]):
        return "\n".join([
            "Oui, je peux vous aider avec ça.",
            "",
            "Pour **Moodle / plateforme / dossier académique**, c’est quoi le problème : accès, document introuvable, module, note, ou suivi administratif ?",
        ])

    return "\n".join([
        "Parfait, merci. Si vous êtes déjà étudiant à l’AMS, je peux vous aider côté parcours et soutien étudiant.",
        "",
        "Qu’est-ce que vous voulez régler aujourd’hui : **cours**, **Moodle**, **horaire**, **matériel/huiles**, **paiement**, **soutien**, ou **prochaine formation** ?",
    ])
