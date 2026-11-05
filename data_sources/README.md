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

The original archive contains 834 distinct OSM IDs and 834 distinct name/coordinate pairs. Public catalog counts describe source records, not independently verified currently operating businesses. The separate web directory adds 55 records; some sources may describe the same physical venue. Unknown prices, menu items, districts and street numbers are never inferred merely to increase completeness.

The collection command downloads map facts; it does not manufacture menus. There are currently only 16 sourced menu-price entries in the separate CSV. Further menu coverage requires actual, attributable merchant/menu evidence.
