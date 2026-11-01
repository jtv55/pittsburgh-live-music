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
