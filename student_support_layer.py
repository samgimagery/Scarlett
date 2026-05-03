"""Deterministic AMS current-student support answers.

This keeps Scarlett from treating active students as either brand-new leads or
already-trained practitioners. The layer only handles clear current-student
support situations; everything else falls through to RAG.
"""
import re
import unicodedata


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("’", "'")
    return re.sub(r"\s+", " ", text).strip()


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
    # Be deliberately strict here. Prospects often ask about "Niveau 1", "formation",
    # "cours", or AMS in general; that must NOT loop them into current-student support.
    # Only route to support when the user explicitly says they are already a student,
    # enrolled, in-progress, or asks about clearly internal student systems like Moodle.
    explicit_student_context = any(x in q for x in [
        "etudiant", "etudiante", "inscrit", "inscrite", "deja inscrit", "deja inscrite",
        "en cours", "je fais", "mon niveau", "ma cohorte", "moodle", "dossier academique",
        "plateforme", "absence", "retard", "facture", "paiement etudiant",
    ])
    asks_student_support = any(x in q for x in support_markers) and explicit_student_context
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
