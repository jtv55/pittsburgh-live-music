"""Refresh pipeline: scrape sources -> normalize -> dedupe -> enrich -> docs/events.json

Run:  python scraper/refresh.py            (full refresh)
      python scraper/refresh.py --no-enrich (skip Deezer lookups)
"""
import json, re, sys, time, math, html, difflib, datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA, DOCS = ROOT / "data", ROOT / "docs"
UA = {"User-Agent": "PittsburghLiveMusicBot/1.0 (+https://github.com/jtv55/pittsburgh-live-music)"}
CENTER = (40.4406, -79.9959)
MAX_MILES = 60
S = requests.Session()
S.headers.update(UA)
TODAY = dt.datetime.now(ZoneInfo("America/New_York")).date()


def get(url, **kw):
    for i in range(3):
        try:
            r = S.get(url, timeout=25, **kw)
            if r.status_code == 200:
                return r
            if r.status_code in (404, 406):
                return None
        except requests.RequestException:
            pass
        time.sleep(1.5 * (i + 1))
    return None


def ldjson(text):
    for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', text, re.S):
        try:
            yield json.loads(b)
        except ValueError:
            pass


def norm(s):
    s = html.unescape(s or "").lower().replace("&", "and")
    s = re.sub(r"\((us|uk|ca|au)\)", "", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(s or "")).strip()


def miles(lat, lon):
    dy = (lat - CENTER[0]) * 69.0
    dx = (lon - CENTER[1]) * 69.0 * math.cos(math.radians(lat))
    return dx, dy, math.hypot(dx, dy)


# ---------------------------------------------------------------- sources

def stageae():
    """Stage AE (North Shore) - AEG/Promowest listing."""
    r = get("https://www.stageae.com/events")
    out = []
    if not r:
        return out
    for chunk in r.text.split("<time")[1:]:
        m = re.search(r'</span>\s*([A-Z][a-z]+ \d{1,2})\s*</time>', chunk)
        t = re.search(r"<h2>(.*?)</h2>\s*(?:<h3>(.*?)</h3>)?", chunk, re.S)
        info = re.search(r'href="(https://promowestlive\.com/pittsburgh/stage-ae/(\d{4})/(\d\d)/[^"]+)"', chunk)
        if not (m and t and info):
            continue
        d = dt.datetime.strptime(f"{m.group(1)} {info.group(2)}", "%B %d %Y").date().isoformat()
        title = clean(t.group(1))
        acts = [clean(x) for x in (t.group(2) or "").split(",") if x.strip()]
        out.append(dict(source="stageae", title=title, artists=acts or [title], date=d, time=None,
                        venue="Stage AE", city="Pittsburgh", address="400 North Shore Dr", lat=40.4467, lon=-80.0054,
                        image=None, url=info.group(1), desc=""))
    return out


def ticketmaster():
    """Official Discovery API. Set TICKETMASTER_API_KEY (free at developer.ticketmaster.com). Skipped if unset."""
    import os
    key = os.environ.get("TICKETMASTER_API_KEY")
    if not key:
        print("  (ticketmaster skipped: no TICKETMASTER_API_KEY)")
        return []
    out = []
    for p in range(0, 10):
        r = S.get("https://app.ticketmaster.com/discovery/v2/events.json", timeout=25, params=dict(
            apikey=key, dmaId=234, classificationName="music", size=200, page=p, sort="date,asc"))
        if r.status_code != 200:
            break
        j = r.json()
        for e in j.get("_embedded", {}).get("events", []):
            v = (e.get("_embedded", {}).get("venues") or [{}])[0]
            at = [x["name"] for x in e.get("_embedded", {}).get("attractions", [])]
            imgs = sorted(e.get("images", []), key=lambda i: -i.get("width", 0))
            loc = v.get("location", {})
            st = e["dates"]["start"]
            if not st.get("localDate"):
                continue
            out.append(dict(source="ticketmaster", title=clean(e["name"]), artists=at or [clean(e["name"])],
                            date=st["localDate"], time=(st.get("localTime") or "")[:5] or None,
                            venue=clean(v.get("name", "")), city=v.get("city", {}).get("name", ""),
                            address=v.get("address", {}).get("line1", ""),
                            lat=float(loc["latitude"]) if loc.get("latitude") else None,
                            lon=float(loc["longitude"]) if loc.get("longitude") else None,
                            image=imgs[0]["url"] if imgs else None, url=e.get("url", ""), desc=""))
        if p + 1 >= j.get("page", {}).get("totalPages", 0):
            break
        time.sleep(0.3)
    return out


NOISE = re.compile(r"church|school|synagogue|congregation|chapel|wedding|banquet|college|university|studio|community center|\bjcc\b|choir|bingo|trivia|workshop|conference", re.I)


def eventbrite():
    out = []
    for p in range(1, 9):
        r = get(f"https://www.eventbrite.com/d/pa--pittsburgh/music--events/?page={p}")
        if not r:
            break
        for d in ldjson(r.text):
            for it in (d.get("itemListElement", []) if isinstance(d, dict) else []):
                e = it.get("item", {})
                loc = e.get("location", {})
                a = loc.get("address", {})
                g = loc.get("geo", {})
                if not e.get("startDate") or not loc.get("name") or not g.get("latitude"):
                    continue
                if miles(float(g["latitude"]), float(g["longitude"]))[2] > 35 or NOISE.search(loc["name"] + " " + e.get("name", "")):
                    continue
                out.append(dict(
                    source="eventbrite", title=clean(e["name"]), artists=[clean(e["name"])],
                    date=e["startDate"][:10], time=(e["startDate"][11:16] or None),
                    venue=clean(loc["name"]), city=a.get("addressLocality", ""), address=a.get("streetAddress", ""),
                    lat=float(g["latitude"]) if g.get("latitude") else None,
                    lon=float(g["longitude"]) if g.get("longitude") else None,
                    image=e.get("image"), url=e.get("url", "").split("?")[0], desc=clean(e.get("description"))))
        time.sleep(0.6)
    return out


def jergels():
    """Jergel's Rhythm Grille (Warrendale) - own calendar, includes shows Songkick misses."""
    out = []
    for p in range(1, 5):
        r = get("https://jergels.com/events/" + (f"page/{p}/" if p > 1 else ""))
        if not r:
            break
        pat = r'<a href="(https://jergels\.com/events/[^"]+)" title="([^"]+)">\s*<div class="article-image">\s*(?:<img src="([^"]*)")?'
        for url, ttl, img in re.findall(pat, r.text):
            ttl = clean(ttl)
            m = re.match(r"(.*) - \w{3}, (\w{3} \d\d, \d{4})$", ttl)
            if not m:
                continue
            d = dt.datetime.strptime(m.group(2), "%b %d, %Y").date().isoformat()
            out.append(dict(source="jergels", title=m.group(1), artists=[m.group(1)], date=d, time=None,
                            venue="Jergel's Rhythm Grille", city="Warrendale", address="2 Perry Hwy",
                            lat=40.6, lon=-80.1, image=img or None, url=url, desc=""))
    return out


def manual():
    f = DATA / "manual_events.json"
    return json.loads(f.read_text("utf8")) if f.exists() else []


# ---------------------------------------------------------------- classify

VENUES = json.loads((DATA / "venues.json").read_text("utf8"))
COVER_NAMES = {norm(l) for l in (DATA / "cover_bands.txt").read_text("utf8").splitlines()
               if l.strip() and not l.startswith("#")}
COVER_RE = re.compile(
    r"\btribute\b|\bcover band\b|\bcovers\b|\bsalute to\b|\bmusic of\b|\bplays the (music|songs|hits)\b"
    r"|\bcover show\b|\bperforming the (music|songs)\b", re.I)


def is_cover(ev):
    if any(norm(a) in COVER_NAMES for a in ev["artists"]) or norm(ev["title"]) in COVER_NAMES:
        return True
    return bool(COVER_RE.search(ev["title"] + " " + ev.get("desc", "")))


def area_of(ev):
    v = VENUES.get(norm(ev["venue"]))
    if v and v.get("area"):
        return v["area"]
    if ev.get("lat") is None:
        return "Central"
    dx, dy, d = miles(float(ev["lat"]), float(ev["lon"]))
    if ev["city"] == "Pittsburgh" or d < 3.0:
        if d < 1.6:
            return "Central"
        if dy > 0.45 and dx < 0.5:
            return "North"
        if dy < -0.4 and dx < 2.5:
            return "South"
        if dx < -3:
            return "West"
        if dx > 5:
            return "East"
        return "Central"
    ang = math.degrees(math.atan2(dx, dy)) % 360  # 0=north, clockwise
    if ang >= 310 or ang < 60:
        return "North"
    if ang < 135:
        return "East"
    if ang < 225:
        return "South"
    return "West"


# ---------------------------------------------------------------- enrich (Deezer: photo + 30s sample)

def enrich(events):
    cf = DATA / "artist_cache.json"
    cache = json.loads(cf.read_text("utf8")) if cf.exists() else {}
    now = time.time()
    for ev in events:
        if ev["cover"]:
            continue  # tribute acts would match the original artist -> wrong photo/audio
        name = ev["artists"][0]
        k = norm(name)
        if not k:
            continue
        c = cache.get(k)
        if not c or now - c["t"] > 30 * 86400:
            c = dict(t=now, hit=None)
            try:
                r = S.get("https://api.deezer.com/search/artist", params={"q": name, "limit": 5}, timeout=15).json()
                m = next((x for x in r.get("data", []) if norm(x["name"]) == k and x.get("nb_fan", 0) >= 1000), None)
                if m:
                    t = S.get(f"https://api.deezer.com/artist/{m['id']}/top", params={"limit": 1},
                              timeout=15).json().get("data", [])
                    c["hit"] = dict(pic=m.get("picture_xl") or m.get("picture_big"), link=m["link"],
                                    track=t[0]["title"] if t else None, preview=t[0]["preview"] if t else None,
                                    tlink=t[0]["link"] if t else None)
                time.sleep(0.12)
            except Exception:
                continue
            cache[k] = c
        h = c["hit"]
        if h:
            ev["photo"] = h["pic"] if h["pic"] and "/artist//" not in h["pic"] else None
            ev["listen"] = dict(track=h["track"], preview=h["preview"], link=h["tlink"] or h["link"])
    cf.write_text(json.dumps(cache), "utf8")


# ---------------------------------------------------------------- main

def main():
    skip_enrich = "--no-enrich" in sys.argv
    raw = []
    for fn in (ticketmaster, stageae, jergels, eventbrite, manual):
        try:
            got = fn()
            print(f"{fn.__name__}: {len(got)}")
            raw += got
        except Exception as ex:
            print(f"{fn.__name__} FAILED: {ex}")  # keep going; other sources still publish
    events = []
    for e in raw:
        if e["date"] < TODAY.isoformat():
            continue
        if e.get("lat") is not None and miles(float(e["lat"]), float(e["lon"]))[2] > MAX_MILES:
            continue
        if e["source"] != "manual" and re.search(
                r"improv|comedy|stand-?up|musical\b|\(tour\)|symphony", e["title"] + " " + e["venue"], re.I):
            continue
        events.append(e)
    rank = {"manual": 0, "jergels": 1, "stageae": 2, "ticketmaster": 3, "eventbrite": 4}
    events.sort(key=lambda e: (e["date"], rank[e["source"]]))
    kept = []
    for e in events:
        dup = False
        for k in kept:
            if k["date"] != e["date"]:
                continue
            same_v = norm(k["venue"])[:6] == norm(e["venue"])[:6]
            ratio = difflib.SequenceMatcher(None, norm(k["artists"][0]), norm(e["artists"][0])).ratio()
            same_title = norm(k["title"]) == norm(e["title"]) and same_v  # multi-night/doubleheader repeats
            if ratio > 0.85 or (same_v and ratio > 0.6) or same_title:
                dup = True
                for f in ("image", "time"):
                    k[f] = k.get(f) or e.get(f)
                break
        if not dup:
            kept.append(e)
    for e in kept:
        e["cover"] = is_cover(e)
        e["area"] = area_of(e)
        e["size"] = VENUES.get(norm(e["venue"]), {}).get("size")
    if not skip_enrich:
        enrich(kept)
    final = []
    for e in kept:
        q = re.sub(r"\s+", "+", e["artists"][0])
        final.append(dict(
            id=f"{e['date']}-{norm(e['artists'][0])[:24]}-{norm(e['venue'])[:10]}", title=e["title"],
            artists=e["artists"][:4], date=e["date"], time=e.get("time"), venue=e["venue"], city=e["city"],
            address=e.get("address"), area=e["area"], cover=e["cover"], size=e.get("size"),
            image=e.get("photo") or e.get("image"), photo=bool(e.get("photo")), url=e["url"],
            listen=e.get("listen"), youtube="https://www.youtube.com/results?search_query=" + q + "+live",
            source=e["source"]))
    final.sort(key=lambda e: (e["date"], e.get("time") or "99"))
    DOCS.mkdir(exist_ok=True)
    (DOCS / "events.json").write_text(json.dumps(dict(
        updated=dt.datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="minutes"),
        count=len(final), events=final), ensure_ascii=False, separators=(",", ":")), "utf8")
    print(f"wrote {len(final)} events; cover={sum(e['cover'] for e in final)}; areas=",
          {a: sum(e['area'] == a for e in final) for a in ("Central", "North", "South", "East", "West")})


if __name__ == "__main__":
    main()
