# Steel City Setlist — Pittsburgh live music

Static site (`docs/`, served by GitHub Pages) + a Python scraper that rebuilds `docs/events.json`.

## Refresh the data
```
pip install -r requirements.txt
python scraper/refresh.py          # add --no-enrich to skip band photo/sample lookups
```
In GitHub, it also runs twice a day via **Actions → Refresh events** (and can be run by hand with *Run workflow*).

## Sources
| Source | Notes |
|---|---|
| Ticketmaster Discovery API | Biggest coverage. Needs a free key: add repo secret `TICKETMASTER_API_KEY`. Skipped when unset. |
| Stage AE, Jergel's Rhythm Grille | Scraped from the venues' own calendars. |
| Eventbrite (Pittsburgh music) | Filtered for churches/schools/etc. |
| Venue registry (`data/sources.json`) | Venues with machine-readable calendars (The Events Calendar plugin, schema.org JSON-LD): Steamworks Creative, Roxian. Venues we can't read yet are listed with `"status": "none"` so gaps stay visible. |
| `data/manual_events.json` | Hand-added shows (see below). |
| Deezer | Band photo + 30s sample, exact-name matches only; tribute acts are never matched. |

## Add a show
Append to `data/manual_events.json`:
```json
{"source":"manual","title":"Band Name","artists":["Band Name"],"date":"2026-12-05","time":"20:00",
 "venue":"Venue","city":"Pittsburgh","address":"123 Main St","lat":40.45,"lon":-79.98,
 "image":null,"url":"https://...","desc":"cover band"}
```
Cover/tribute flagging: keywords in the title/description plus `data/cover_bands.txt`. Area overrides per venue: `data/venues.json`.

## Adding a venue scraper
Write a function in `scraper/refresh.py` returning dicts in the shape above and add it to the `for fn in (...)` list.

## Genres
Each event gets one genre bucket. Priority: manual override (`data/genres.json`) > Ticketmaster genre / Deezer album genre > title keywords (`scraper/genres.py`) > `Other`. Fix a wrong or missing one by adding the artist to `data/genres.json`.

## Adding a venue
If the site uses The Events Calendar (`/wp-json/tribe/events/v1/events` works) or embeds schema.org Event JSON-LD, add an entry to `data/sources.json` with `"status": "scraped"` and `"type": "tribe"` or `"ldjson"`. No code needed.
