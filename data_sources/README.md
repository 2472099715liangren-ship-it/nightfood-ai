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

~~~bash
python3 osm_sync.py fetch --output data_sources/osm_wuhan_snapshot.json
python3 -m unittest discover -s tests -v
~~~

The site imports a committed snapshot at startup into the independent real_merchants SQLite table using a checksum guard. Demo data remains separate.

**Attribution must remain visible near OSM-derived results**, and this document must stay in the repository. See https://osmfoundation.org/wiki/Attribution_Guidelines .
