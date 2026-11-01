"""Genre bucketing. Priority: manual override > upstream tag (Ticketmaster/Deezer) > title keywords > venue default."""
import json
import re
from pathlib import Path

GENRES = ["Rock", "Metal & Punk", "Hip-Hop & R&B", "Country & Folk", "Jazz & Blues", "Electronic & Dance",
          "Pop", "Indie & Alt", "Latin & World", "Classical"]

# upstream genre label substring -> bucket (first hit wins)
LABELS = [
    ("metal", "Metal & Punk"), ("punk", "Metal & Punk"), ("hardcore", "Metal & Punk"), ("emo", "Metal & Punk"),
    ("hip", "Hip-Hop & R&B"), ("rap", "Hip-Hop & R&B"), ("r&b", "Hip-Hop & R&B"), ("soul", "Hip-Hop & R&B"),
    ("funk", "Hip-Hop & R&B"), ("country", "Country & Folk"), ("folk", "Country & Folk"),
    ("bluegrass", "Country & Folk"), ("americana", "Country & Folk"), ("singer", "Country & Folk"),
    ("jazz", "Jazz & Blues"), ("blues", "Jazz & Blues"), ("dance", "Electronic & Dance"),
    ("electro", "Electronic & Dance"), ("edm", "Electronic & Dance"), ("techno", "Electronic & Dance"),
    ("house", "Electronic & Dance"), ("indie", "Indie & Alt"), ("alternative", "Indie & Alt"),
    ("latin", "Latin & World"), ("reggae", "Latin & World"), ("world", "Latin & World"),
    ("classical", "Classical"), ("opera", "Classical"), ("orchestra", "Classical"),
    ("pop", "Pop"), ("rock", "Rock"),
]

# title/description keywords, checked in this order
KEYWORDS = [
    ("Metal & Punk", r"\b(metal|punk|hardcore|ska|screamo|thrash|deathcore|emo|grindcore)\b|pop punk"),
    ("Hip-Hop & R&B", r"\b(hip.?hop|rap|r&b|soul|funk|trap)\b"),
    ("Country & Folk", r"\b(country|bluegrass|folk|americana|honky.?tonk|celtic|acoustic|singer.?songwriter|nashville)\b"),
    ("Jazz & Blues", r"\b(jazz|blues|swing|sax)\b"),
    ("Electronic & Dance", r"\b(dj|edm|techno|house|trance|dubstep|rave|dance party|club night)\b"),
    ("Latin & World", r"\b(latin|salsa|cumbia|reggae|banda|conjunto|persian|afro|bhangra|kizomba|clave)\b"),
    ("Classical", r"\b(symphony|orchestra|philharmonic|choir|choral|opera|chamber|quartet|chorale|wind ensemble)\b"),
    ("Indie & Alt", r"\b(indie|alternative|shoegaze|grunge)\b"),
    ("Pop", r"\b(pop|boy band|k-?pop|backstreet|nsync|swift|swifties)\b"),
    ("Rock", r"\b(rock|classic rock|arena rock|jam band|rockabilly|grateful|zeppelin|beatles|creedence|led zeppelin)\b"),
]
KEYWORDS = [(b, re.compile(p, re.I)) for b, p in KEYWORDS]


def _norm(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def bucket(label):
    low = (label or "").lower()
    return next((b for sub, b in LABELS if sub in low), None)


def load_overrides(path: Path):
    return {_norm(k): v for k, v in json.loads(path.read_text("utf8")).items()} if path.exists() else {}


def genre_of(ev, overrides, venue_default=None):
    for a in ev["artists"][:2] + [ev["title"]]:
        if _norm(a) in overrides:
            return overrides[_norm(a)]
    for lab in [ev.get("tmgenre")] + (ev.get("dgenres") or []):
        if bucket(lab):
            return bucket(lab)
    text = ev["title"] + " " + ev.get("desc", "")
    for b, rx in KEYWORDS:
        if rx.search(text):
            return b
    return venue_default or "Other"
