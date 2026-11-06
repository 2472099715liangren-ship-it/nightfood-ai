/* Local WGS84 basemap and source coordinates share one projection.
 * Geographic sources and limitations: static/map/README.md.
 * No API key, remote JavaScript, or online tiles are needed for the default map.
 */
window.NightFindWuhanMap = (() => {
  "use strict";
  let map, markerLayer, labelLayer, currentContainer, allBounds;
  let generation = 0;
  let basemapRequest;
  let settingsRequest;
  let routeLayer;
  const markers = new Map();
  const escape = (value) =>
    String(value ?? "").replace(
      /[&<>"']/g,
      (char) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[char],
    );

  function dispose() {
    generation += 1;
    if (map) map.remove();
    map =
      markerLayer =
      labelLayer =
      currentContainer =
      allBounds =
      routeLayer =
        null;
    markers.clear();
  }

  function loadBasemap() {
    if (!basemapRequest) {
      basemapRequest = fetch("/map/wuhan-basemap.geojson")
        .then((response) => {
          if (!response.ok) throw new Error("武汉底图文件读取失败");
          return response.json();
        })
        .catch((error) => {
          basemapRequest = null; // Allow a retry after a temporary local server error.
          throw error;
        });
    }
    return basemapRequest;
  }

  function addBasemap(data) {
    const group = (layer) => ({
      type: "FeatureCollection",
      features: data.features.filter(
        (feature) => feature.properties.layer === layer,
      ),
    });
    const vector = (layer, style) =>
      L.geoJSON(group(layer), {
        style,
        interactive: false,
        pane: "basemap",
      }).addTo(map);
    vector("boundary", {
      color: "#b6c7ae",
      weight: 1,
      fillColor: "#edf1e7",
      fillOpacity: 0.7,
    });
    vector("lake", {
      color: "#a5cbd0",
      weight: 1,
      fillColor: "#b4d7d9",
      fillOpacity: 0.9,
    });
    vector("river", { color: "#afd0d6", weight: 12, opacity: 1 });
    vector("road", { color: "#d7d8c9", weight: 5, opacity: 1 });
    vector("road", { color: "#fffdf4", weight: 2.5, opacity: 1 });
    labelLayer = L.layerGroup().addTo(map);
    const labelFeatures = data.features.filter(
      (feature) =>
        ["road", "park", "station", "water_label"].includes(
          feature.properties.layer,
        ) && feature.properties.name,
    );

    // Screen-space spacing keeps place names readable at every zoom level.
    function updateLabels() {
      labelLayer.clearLayers();
      const occupied = new Set();
      const zoom = map.getZoom();
      for (const feature of labelFeatures) {
        const { layer, name } = feature.properties;
        if (zoom < (layer === "station" ? 14 : layer === "park" ? 13 : 10))
          continue;
        const coords =
          feature.geometry.type === "Point"
            ? feature.geometry.coordinates
            : feature.geometry.coordinates[
                Math.floor(feature.geometry.coordinates.length / 2)
              ];
        const point = L.latLng(coords[1], coords[0]);
        if (!map.getBounds().contains(point)) continue;
        const pixel = map.latLngToContainerPoint(point);
        const cell = `${Math.floor(pixel.x / 105)}:${Math.floor(pixel.y / 36)}`;
        if (occupied.has(cell)) continue;
        occupied.add(cell);
        L.marker(point, {
          interactive: false,
          pane: "placeLabels",
          icon: L.divIcon({
            className: `map-place-label label-${layer}`,
            html: escape(name),
            iconSize: [100, 20],
            iconAnchor: [50, 10],
          }),
        }).addTo(labelLayer);
      }
    }
    map.on("zoomend moveend", updateLabels);
    updateLabels();
  }

  async function tryStreetTiles(container, version) {
    if (!settingsRequest)
      settingsRequest = fetch("/api/map-config")
        .then((response) => (response.ok ? response.json() : {}))
        .catch(() => ({}));
    const settings = await settingsRequest;
    if (version !== generation) return;

    function addProvider(provider) {
      const options = { maxZoom: 18, pane: "streetTiles" };
      const layers =
        provider === "tianditu"
          ? ["vec", "cva"].map((layer) =>
              L.tileLayer(
                `https://t{s}.tianditu.gov.cn/${layer}_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=${layer}&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&tk=${encodeURIComponent(settings.tianditu_key)}`,
                {
                  ...options,
                  subdomains: "01234567",
                  attribution:
                    '© <a href="https://www.tianditu.gov.cn/" target="_blank" rel="noopener noreferrer">天地图</a>',
                },
              ),
            )
          : [
              L.tileLayer(
                "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                options,
              ),
            ];
      const group = L.layerGroup(layers);
      let failed = false;
      const ready = new Set();
      container.dataset.streets = "loading";
      for (const layer of layers) {
        layer.on("tileerror", () => {
          if (version !== generation || failed) return;
          failed = true;
          group.remove();
          map.getPane("placeLabels").style.opacity = "1";
          if (provider === "tianditu") return addProvider("osm");
          container.dataset.streets = "unavailable";
          container.dataset.provider = "offline";
        });
        layer.on("load", () => {
          if (version !== generation || failed) return;
          ready.add(layer);
          if (ready.size !== layers.length) return;
          map.getPane("placeLabels").style.opacity = "0";
          container.dataset.streets = "ready";
          container.dataset.provider = provider;
        });
      }
      group.addTo(map);
    }
    // Both TianDiTu's CGCS2000 Web Mercator and OSM align with our WGS84
    // geographic points at this scale. Never put GCJ-02 points on this map.
    addProvider(settings.tianditu_key ? "tianditu" : "osm");
  }

  function popup(item, lat, lng) {
    const price =
      item.price_per_person != null
        ? `参考人均 ¥${item.price_per_person}`
        : item.price_range_min != null && item.price_range_max != null
          ? `${item.price_range_basis === "dish" ? "菜品参考价" : "来源参考价"} ¥${item.price_range_min}–${item.price_range_max}`
          : "尚未收录参考价格";
    return `<div class="real-map-popup"><span class="eyebrow">武汉 · 真实商家</span>
      <h3>${escape(item.name)}</h3><p>${escape(item.address || item.district || "来源坐标点位")}</p>
      <p class="map-popup-price">${escape(price)}</p>
      ${(item.priced_menu || []).map((dish) => `<p>${escape(dish.dish_name)} ¥${escape(dish.price)} ${escape(dish.price_unit)}</p>`).join("")}
      <small>${lat.toFixed(6)}, ${lng.toFixed(6)} · WGS84<br>${escape(item.source_name || "公开来源")} · 非实时营业信息</small>
      <button type="button" class="button-primary" data-real-merchant="${Number(item.id)}">查看完整资料 ↗</button></div>`;
  }

  async function draw(container, restaurants, { overview = false } = {}) {
    if (!container || !window.L) return { available: false, pins: 0 };
    if (currentContainer && currentContainer !== container)
      currentContainer.hidden = true;
    dispose();
    container.hidden = false;
    const version = generation;
    currentContainer = container;
    container.dataset.basemap = "loading";
    map = L.map(container, {
      preferCanvas: true,
      minZoom: 9,
      maxZoom: 18,
      scrollWheelZoom: false,
    }).setView([30.585, 114.3], 11);
    map.createPane("basemap").style.zIndex = 200;
    map.createPane("streetTiles").style.zIndex = 250;
    map.createPane("placeLabels").style.zIndex = 450;
    map.getPane("placeLabels").style.pointerEvents = "none";
    map.attributionControl.addAttribution(
      '底图：© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> · <a href="https://www.naturalearthdata.com/about/terms-of-use/" target="_blank" rel="noopener noreferrer">Natural Earth</a>',
    );
    L.control.scale({ imperial: false, position: "bottomleft" }).addTo(map);
    markerLayer = L.layerGroup().addTo(map);
    const bounds = [];
    for (const item of restaurants) {
      const lat = Number(item.latitude),
        lng = Number(item.longitude);
      if (
        item.latitude == null ||
        item.longitude == null ||
        !Number.isFinite(lat) ||
        !Number.isFinite(lng) ||
        lat < 29.8 ||
        lat > 31.5 ||
        lng < 113.5 ||
        lng > 115.2
      )
        continue;
      const marker = L.circleMarker([lat, lng], {
        radius: 6,
        color: "#fffef9",
        weight: 2,
        fillColor: "#4f805f",
        fillOpacity: 0.9,
      }).addTo(markerLayer);
      marker.bindPopup(popup(item, lat, lng), { maxWidth: 290 });
      marker.on("popupopen", () =>
        marker.setStyle({ radius: 9, fillColor: "#244d3b" }),
      );
      marker.on("popupclose", () =>
        marker.setStyle({ radius: 6, fillColor: "#4f805f" }),
      );
      markers.set(Number(item.id), marker);
      bounds.push([lat, lng]);
    }
    allBounds = bounds.length ? L.latLngBounds(bounds).pad(0.12) : null;
    if (!overview && allBounds)
      map.fitBounds(allBounds, { maxZoom: 14, animate: false });
    container.dataset.pins = bounds.length;
    try {
      const data = await loadBasemap();
      if (version !== generation || !container.isConnected)
        return { available: false, pins: 0 };
      addBasemap(data);
      container.dataset.basemap = "ready";
      tryStreetTiles(container, version);
    } catch {
      if (version !== generation) return { available: false, pins: 0 };
      container.dataset.basemap = "error";
      // Clearly report a missing local asset; never present a blank canvas as a loaded map.
      const notice = L.control({ position: "topright" });
      notice.onAdd = () => {
        const element = L.DomUtil.create("div", "map-load-error");
        element.textContent =
          "武汉底图文件读取失败，请刷新页面；仍可打开商家导航。";
        return element;
      };
      notice.addTo(map);
    }
    map.invalidateSize();
    return { available: true, pins: bounds.length };
  }

  function focus(id) {
    const marker = markers.get(Number(id));
    if (!map || !marker) return false;
    map.setView(marker.getLatLng(), 15, { animate: false });
    marker.openPopup();
    currentContainer.scrollIntoView({ behavior: "smooth", block: "center" });
    return true;
  }

  function fitAll() {
    if (map && allBounds)
      map.fitBounds(allBounds, { maxZoom: 14, animate: false });
  }
  function view() {
    if (!map) return null;
    const center = map.getCenter();
    return { latitude: center.lat, longitude: center.lng, zoom: map.getZoom() };
  }

  function restoreView(value) {
    if (
      map &&
      value &&
      Number.isFinite(value.latitude) &&
      Number.isFinite(value.longitude)
    )
      map.setView([value.latitude, value.longitude], value.zoom, {
        animate: false,
      });
  }

  function showRoute(points) {
    if (!map || !points?.length) return;
    if (routeLayer) routeLayer.remove();
    routeLayer = L.polyline(points, {
      color: "#486d91",
      weight: 5,
      opacity: 0.85,
    }).addTo(map);
    map.fitBounds(routeLayer.getBounds().pad(0.15), {
      maxZoom: 16,
      animate: false,
    });
  }
  return { draw, dispose, focus, fitAll, view, restoreView, showRoute };
})();
