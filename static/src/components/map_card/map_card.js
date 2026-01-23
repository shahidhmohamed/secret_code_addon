/** @odoo-module */

import { loadCSS, loadJS } from "@web/core/assets";
const { Component, onMounted, onWillStart, onWillUpdateProps, useRef } = owl;

export class MapCard extends Component {
  setup() {
    this.mapRef = useRef("map");
    this.map = null;
    this.markerLayer = null;
    onWillStart(async () => {
      await loadCSS("https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.css");
      await loadJS("https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.js");
    });

    onMounted(() => this._initMap());
    onWillUpdateProps((nextProps) => {
      if (this.map) {
        this._renderMarkers(nextProps.points);
      }
    });
  }

  _initMap() {
    if (!this.mapRef.el || !window.L) {
      return;
    }

    const points = Array.isArray(this.props.points) ? this.props.points : [];
    const first = points[0];
    const center = first ? [first.lat, first.lng] : [25.2048, 55.2708];

    const map = L.map(this.mapRef.el, {
      zoomControl: true,
      scrollWheelZoom: true,
      preferCanvas: true,
    }).setView(center, first ? 5 : 3);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);
    this.map = map;
    this.markerLayer = L.layerGroup().addTo(map);
    this._renderMarkers(points);
    setTimeout(() => map.invalidateSize(), 0);
  }

  _renderMarkers(pointsInput) {
    const points = Array.isArray(pointsInput) ? pointsInput : [];
    if (!this.map || !this.markerLayer) {
      return;
    }

    this.markerLayer.clearLayers();
    const bounds = [];
    const coordCount = new Map();
    const defaultIcon = L.icon({
      iconUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png",
      iconRetinaUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png",
      shadowUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png",
      iconSize: [25, 41],
      iconAnchor: [12, 41],
      popupAnchor: [1, -34],
      shadowSize: [41, 41],
    });
    points.forEach((point) => {
      const baseLat = Number(point?.lat);
      const baseLng = Number(point?.lng);
      if (!Number.isFinite(baseLat) || !Number.isFinite(baseLng)) {
        return;
      }
      const key = `${baseLat},${baseLng}`;
      const idx = coordCount.get(key) || 0;
      coordCount.set(key, idx + 1);
      const jitter = idx === 0 ? 0 : 0.00025 * Math.sqrt(idx);
      const angle = idx * 1.8;
      const lat = baseLat + jitter * Math.cos(angle);
      const lng = baseLng + jitter * Math.sin(angle);
      const latlng = [lat, lng];
      bounds.push(latlng);
      const marker = L.marker(latlng, { icon: defaultIcon }).addTo(this.markerLayer);
      const status = point?.status || "unknown";
      marker.bindPopup(`Status: ${status}`);
    });

    if (bounds.length > 1) {
      this.map.fitBounds(bounds, { padding: [24, 24], maxZoom: 8 });
    } else if (bounds.length === 1) {
      this.map.setView(bounds[0], 6);
    }
  }
}

MapCard.props = ["title", "points"];
MapCard.template = "owl.MapCard";
