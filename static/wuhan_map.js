/* Wuhan real-restaurant map, intentionally loaded only when visitor opens Map.
 * Tiles: OSM for low-traffic local development only. Replace provider before
 * public scale-up. See https://operations.osmfoundation.org/policies/tiles/.
 */
window.NightFindWuhanMap = (function () {
  "use strict";
  let map = null;
  let markerLayer = null;
  let currentContainer = null;

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (char) {
      return {
        "&": "&amp;", "<": "&lt;", ">": "&gt;",
        '"': "&quot;", "'": "&#39;"
      }[char];
    });
  }

  function dispose() {
    if (map) map.remove();
    map = null;
    markerLayer = null;
    currentContainer = null;
  }

  function draw(container, restaurants) {
    if (!container) return { available: false, pins: 0 };
    if (!window.L) {
      container.innerHTML =
        '<div class="empty-state">地图组件暂时无法加载。请检查网络连接，仍可使用列表浏览真实门店。</div>';
      return { available: false, pins: 0 };
    }
    if (currentContainer !== container) {
      dispose();
      map = L.map(container, { preferCanvas: true, zoomControl: true })
        .setView([30.59, 114.30], 10);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 18,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap contributors</a>'
      }).addTo(map);
      currentContainer = container;
      markerLayer = L.layerGroup().addTo(map);
    }
    markerLayer.clearLayers();
    const bounds = [];
    restaurants.forEach(function (restaurant) {
      const lat = Number(restaurant.latitude);
      const lng = Number(restaurant.longitude);
      if (!Number.isFinite(lat) || !Number.isFinite(lng) ||
          restaurant.latitude == null || restaurant.longitude == null) return;
      if (lat < 29.8 || lat > 31.5 || lng < 113.5 || lng > 115.2) return;

      const verified = restaurant.data_quality === "verified";
      const community = restaurant.data_quality === "community";
      const marker = L.circleMarker([lat, lng], {
        radius: 9,
        color: verified ? "#3f6a49" : community ? "#718a9c" : "#9b8058",
        fillColor: verified ? "#80a97e" : community ? "#a9c1d0" : "#d8c39b",
        fillOpacity: 0.92,
        weight: 2
      }).addTo(markerLayer);
      const price = restaurant.price_per_person != null
        ? "人均约 ¥" + restaurant.price_per_person
        : restaurant.price_range_min != null && restaurant.price_range_max != null
          ? "参考价 ¥" + restaurant.price_range_min + "–" + restaurant.price_range_max
          : "价格待核实";
      const quality = verified ? "人工核验通过" :
        community ? "OSM 社区收录 · 营业状态未核实" : "网页收录 · 营业状态未人工核实";
      marker.bindPopup(
        '<div class="real-map-popup"><strong>' + escapeHtml(restaurant.name) +
        '</strong><p>' + escapeHtml(restaurant.district) + " · " +
        escapeHtml(restaurant.address) + '</p><span class="real-map-quality ' +
        (verified ? "verified" : community ? "community" : "web-listing") + '">' + escapeHtml(quality) +
        '</span><p>' + escapeHtml(price) + " · 来源核查 " +
        escapeHtml(restaurant.source_checked_at || "未记录") +
        '</p><button type="button" data-real-merchant="' +
        restaurant.id + '">查看门店资料 →</button></div>'
      );
      bounds.push([lat, lng]);
    });
    if (bounds.length) {
      map.fitBounds(L.latLngBounds(bounds).pad(0.17), { maxZoom: 14 });
    } else {
      map.setView([30.59, 114.30], 10);
    }
    window.requestAnimationFrame(function () {
      if (map) map.invalidateSize();
    });
    return { available: true, pins: bounds.length };
  }

  return { draw: draw, dispose: dispose };
})();
