# Wuhan OpenStreetMap community POI snapshot

**Source:** © OpenStreetMap contributors · [Open Database License 1.0 (ODbL)](https://www.openstreetmap.org/copyright).

The repository snapshot osm_wuhan_snapshot.json (when present) is an extract from the OpenStreetMap database via the public Overpass API. It is made available under the ODbL; keep this notice and a working attribution link when redistributing or using the extract. ODbL may require sharing any adapted database under the same licence. Review the ODbL obligations before combining it with proprietary datasets.

- Geographic query: Wuhan city administrative area (name=武汉市, boundary=administrative).
- Categories: mapped restaurants, fast food, cafés and food courts with names.
- Provenance: each row includes a direct OSM element link (node, way or relation).
- Completeness: OSM is community-maintained and incomplete, especially for individual restaurants and addresses. Absence in OSM is not evidence that a business does not exist.
- Verification: **not independently checked**; these records have status=pending, displayed as community mapped, not verified.
- Prices, waiting times and ratings are not inferred and may be missing. Opening hours are shown only if mapped and are not real-time verified.
- Extraction is deliberately initiated, not continuously scraping on every site request.

Data collection is a one-time best-effort fetch from the public Overpass servers. Public servers may reject or limit requests; if the fetch fails, do not invent or seed placeholder businesses.

To rebuild deliberately:

```bash
python3 osm_sync.py fetch --output data_sources/osm_wuhan_snapshot.json
python3 -m unittest discover -s tests -v
```

The site imports source records into the independent real_merchants SQLite table using a checksum guard. Normal startup creates no demo merchants. Historical sample records are backed up before removal.

**Attribution must remain visible near OSM-derived results**, and this document must stay in the repository. See https://osmfoundation.org/wiki/Attribution_Guidelines .

## Five-year online evidence and the bundled archive

The bundled JSON was archived in repository commit `5389d9bba6a63bd953e90770f1fb0c6d3e7622e2` on **2026-11-02**. Its companion `.meta.json` pins the exact SHA-256 and source record count. This date is evidence of repository archival, not a field survey or a claim that each venue is operating today. The underlying OSM JSON and its missing survey dates are unchanged.

Public read rules now admit dated online collections and source archives from the past five calendar years. Web and survey dates remain separate. The two-year rule is retained for licensed photographs. A newly fetched live collection is stored in `wuhan_live_catalog.json` with its own collection date and content digest. Failed or undersized downloads leave existing data intact.

The original archive contains 834 distinct OSM IDs and 834 distinct name/coordinate pairs. Public catalog counts describe source records, not independently verified currently operating businesses. The separate web directory adds 68 records; some sources may describe the same physical venue. Unknown prices, menu items, districts and street numbers are never inferred merely to increase completeness.

The collection command downloads map facts; it does not manufacture menus. The web refresh on 2026-11-06 increased the separate CSV to 74 sourced menu-price entries across 21 merchants, with 18 of those merchants having coordinates. Further menu coverage requires actual, attributable merchant/menu evidence.

## Web refresh — 2026-11-06

`wuhan_web_refresh.json` contains the used factual source fields and HTML SHA-256 values from 46 successfully parsed public Ctrip branch pages, plus errors for 4 skipped pages. It keeps original `GDCoord` coordinates and recommended dish prices. The CSV stores converted WGS84 points; original 55 web records are preserved, and 13 records are added (68 web + 834 OSM = 902 source records, 887 mapped points). Counts describe source records; sources can describe the same physical venue. No new OSM live collection is claimed.

The refresh imports only branch-matched facts, never a brand-wide price. Dish amounts without serving size retain the explicit label “来源未注明份量”. The displayed average is a reference per-person value from that exact source page. Ctrip images, ratings, customer reviews, live open indicators and tracking fields are not imported.

Re-run with `python3 refresh_wuhan_catalog.py --apply --discover --limit 50`. No login or private endpoints are used. Failed pages preserve existing entries; unknown administrative districts remain unknown. A source capture date is not a business-opening guarantee.
