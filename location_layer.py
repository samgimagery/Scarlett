"""
Local location layer for Scarlett / AMS.

Fixed business facts (campuses) + a small built-in Quebec place gazetteer.
No internet, no live routing: we rank by straight-line distance and phrase that
clearly as an orientation estimate for a receptionist.
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Point:
    name: str
    lat: float
    lon: float
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class Campus(Point):
    address: str = ""


CAMPUSES: tuple[Campus, ...] = (
    Campus("Montréal", 45.5450, -73.6065, ("montreal",), "910 rue Bélanger Est, suite 202"),
    Campus("Québec", 46.7875, -71.2858, ("quebec", "ville de quebec", "québec city", "quebec city"), "2323, boul. Versant Nord, bureau 115"),
    Campus("Laval", 45.5585, -73.7440, (), "1800, boul. Le Corbusier, bureau 135"),
    Campus("Brossard", 45.4725, -73.4690, (), "6185, boul. Taschereau, bureau 210"),
    Campus("Sherbrooke", 45.3970, -71.9180, (), "740, rue Galt Ouest, bureau 011"),
    Campus("Terrebonne", 45.7005, -73.6415, (), "1160, rue Lévis, suite 100"),
    Campus("Drummondville", 45.8956, -72.5143, ("drummond",), "1375, rue Janelle, 2e étage"),
    Campus("Trois-Rivières", 46.3490, -72.5821, ("trois rivieres", "trois-rivieres", "3-rivieres", "3 rivieres"), "3910, boul. des Forges, bureau 204"),
)

# Seed gazetteer. Add places here as customers ask; campus cities are included too.
PLACES: tuple[Point, ...] = (
    *(Point(c.name, c.lat, c.lon, c.aliases) for c in CAMPUSES),
    Point("Saint-Lazare", 45.4000, -74.1330, ("st-lazare", "st lazare", "saint lazare", "saint-lazar", "saint lazar", "st-lazar", "st lazar")),
    Point("Vaudreuil-Dorion", 45.4000, -74.0330, ("vaudreuil",)),
    Point("Hudson", 45.4500, -74.1500, ()),
    Point("Pincourt", 45.3830, -73.9830, ()),
    Point("Île-Perrot", 45.3830, -73.9500, ("ile-perrot", "ile perrot", "l'ile-perrot", "l ile perrot")),
    Point("Salaberry-de-Valleyfield", 45.2500, -74.1330, ("valleyfield",)),
    Point("Châteauguay", 45.3830, -73.7500, ("chateauguay",)),
    Point("Beauharnois", 45.3170, -73.8670, ()),
    Point("Kirkland", 45.4500, -73.8670, ()),
    Point("Pointe-Claire", 45.4500, -73.8170, ("pointe claire",)),
    Point("Dorval", 45.4500, -73.7500, ()),
    Point("Longueuil", 45.5330, -73.5170, ()),
    Point("Boucherville", 45.6000, -73.4500, ()),
    Point("Saint-Hyacinthe", 45.6300, -72.9570, ("st-hyacinthe", "st hyacinthe", "saint hyacinthe")),
    Point("Granby", 45.4000, -72.7330, ()),
    Point("Magog", 45.2670, -72.1500, ()),
    Point("Victoriaville", 46.0500, -71.9670, ()),
    Point("Sorel-Tracy", 46.0330, -73.1170, ("sorel",)),
    Point("Repentigny", 45.7420, -73.4500, ()),
    Point("Mascouche", 45.7500, -73.6000, ()),
    Point("Mirabel", 45.6500, -74.0830, ()),
    Point("Saint-Jérôme", 45.7830, -74.0000, ("st-jerome", "st jerome", "saint jerome")),
    Point("Blainville", 45.6700, -73.8800, ()),
    Point("Boisbriand", 45.6170, -73.8330, ()),
    Point("Saint-Eustache", 45.5670, -73.9000, ("st-eustache", "st eustache", "saint eustache")),
    Point("Gatineau", 45.4770, -75.7010, ()),
    Point("Rimouski", 48.4500, -68.5300, ()),
    Point("Saguenay", 48.4280, -71.0680, ("chicoutimi", "jonquiere", "jonquière")),
    Point("Rouyn-Noranda", 48.2399, -79.0204, ("rouyn", "rouyn noranda")),
)


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("’", "'")
    text = re.sub(r"[^a-z0-9' -]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _haversine_km(a: Point, b: Point) -> float:
    r = 6371.0
    lat1, lon1 = math.radians(a.lat), math.radians(a.lon)
    lat2, lon2 = math.radians(b.lat), math.radians(b.lon)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _names(point: Point) -> Iterable[str]:
    yield point.name
    yield from point.aliases


def find_place(question: str) -> Point | None:
    q = f" {_norm(question)} "
    matches: list[tuple[int, Point]] = []
    for place in PLACES:
        for name in _names(place):
            n = _norm(name)
            if n and f" {n} " in q:
                matches.append((len(n), place))
                break
    if not matches:
        return None
    return sorted(matches, key=lambda x: x[0], reverse=True)[0][1]


def ranked_campuses(origin: Point, limit: int = 3) -> list[tuple[Campus, float]]:
    rows = [(campus, _haversine_km(origin, campus)) for campus in CAMPUSES]
    return sorted(rows, key=lambda row: row[1])[:limit]


def is_campus_location_query(question: str) -> bool:
    q = _norm(question)
    campus_words = ("campus", "college", "colleges", "ecole", "ecoles", "lieu", "lieux", "adresse")
    location_words = ("plus pres", "proche", "pres de", "chez moi", "ville", "liste", "ou sont", "adresses", "adresse", "quels", "quelles")
    return any(w in q for w in campus_words) and any(w in q for w in location_words)


def answer_location(question: str) -> str | None:
    if not is_campus_location_query(question):
        return None

    q = _norm(question)
    asks_list = any(w in q for w in ("liste", "tous", "toutes", "quels", "quelles", "ou sont", "adresses"))
    origin = find_place(question)

    if asks_list and not origin:
        rows = "\n".join(f"- **{c.name}** — {c.address}" for c in CAMPUSES)
        return (
            "L’AMS a **8 campus au Québec** :\n\n"
            f"{rows}\n\n"
            "Si vous me donnez votre ville, je peux vous indiquer lequel est probablement le plus proche."
        )

    if origin:
        nearest = ranked_campuses(origin, limit=3)
        best, best_km = nearest[0]
        rows = "\n".join(f"- {campus.name} — environ {km:.0f} km" for campus, km in nearest)
        return (
            f"Depuis **{origin.name}**, le campus AMS le plus proche est probablement **{best.name}**.\n\n"
            f"**Adresse** : {best.address}\n\n"
            f"Repères à vol d’oiseau :\n{rows}\n\n"
            "C’est une estimation locale, pas un calcul de trajet en temps réel. Si la personne se déplace en transport en commun, je recommanderais de valider entre les deux premiers campus."
        )

    if asks_list:
        rows = "\n".join(f"- **{c.name}** — {c.address}" for c in CAMPUSES)
        return f"L’AMS a **8 campus au Québec** :\n\n{rows}"

    return (
        "Je connais les 8 campus AMS, mais je n’ai pas reconnu la ville dans votre message. "
        "Donnez-moi simplement votre ville — par exemple Saint-Lazare, Laval ou Sherbrooke — et je vous indique le campus probablement le plus proche."
    )
