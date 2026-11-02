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

      const marker = L.circleMarker([lat, lng], {
        radius: 9,
        color: "#3f6a49",
        fillColor: "#80a97e",
        fillOpacity: 0.9,
        weight: 2
      }).addTo(markerLayer);
      const price = restaurant.price_per_person == null
        ? "人均待核实" : "人均约 ¥" + restaurant.price_per_person;
      marker.bindPopup(
        '<div class="real-map-popup"><strong>' + escapeHtml(restaurant.name) +
        '</strong><p>' + escapeHtml(restaurant.district) + " · " +
        escapeHtml(restaurant.address) + '</p><span>' +
        escapeHtml(price) + '</span><button type="button" data-real-merchant="' +
        restaurant.id + '">查看已核验资料 →</button></div>'
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
