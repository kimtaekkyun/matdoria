"use client";

import { createPortal } from "react-dom";
import { useEffect, useRef, useState } from "react";
import type { Place } from "../lib/types";
import type { MapInsets } from "../lib/mobileLayout";
import PlaceDetail from "./PlaceDetail";

type KakaoProjection = {
  containerPointFromCoords(position: unknown): { x: number; y: number };
  coordsFromContainerPoint(point: unknown): unknown;
};

type KakaoMapInstance = {
  relayout(): void;
  setBounds(bounds: KakaoBounds, paddingTop?: number, paddingRight?: number, paddingBottom?: number, paddingLeft?: number): void;
  panTo(position: unknown): void;
  getProjection(): KakaoProjection;
};

type KakaoMarker = {
  setMap(map: KakaoMapInstance | null): void;
  setImage(image: unknown): void;
  setZIndex(zIndex: number): void;
};

type KakaoOverlay = {
  setMap(map: KakaoMapInstance | null): void;
};

type KakaoBounds = {
  extend(position: unknown): void;
};

type KakaoNamespace = {
  maps: {
    load(callback: () => void): void;
    Map: new (container: HTMLElement, options: { center: unknown; level: number }) => KakaoMapInstance;
    LatLng: new (lat: number, lng: number) => unknown;
    LatLngBounds: new () => KakaoBounds;
    MarkerImage: new (image: string, size: unknown, options: { offset: unknown }) => unknown;
    Size: new (width: number, height: number) => unknown;
    Point: new (x: number, y: number) => unknown;
    Marker: new (options: { position: unknown; title: string; image: unknown; zIndex: number }) => KakaoMarker;
    CustomOverlay: new (options: {
      position: unknown;
      content: HTMLElement;
      xAnchor: number;
      yAnchor: number;
      zIndex: number;
      clickable: boolean;
    }) => KakaoOverlay;
    event: {
      addListener(target: KakaoMarker, event: string, callback: () => void): void;
    };
  };
};

declare global {
  interface Window {
    kakao?: KakaoNamespace;
  }
}

const SEOUL_CENTER = { lat: 37.5665, lng: 126.978 };
const SDK_ID = "kakao-map-sdk";

function loadKakaoSdk(appKey: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const loadedKakao = window.kakao;
    if (loadedKakao?.maps) {
      loadedKakao.maps.load(() => resolve());
      return;
    }
    const existing = document.getElementById(SDK_ID) as HTMLScriptElement | null;
    const onLoad = () => {
      const kakao = window.kakao;
      if (!kakao?.maps) {
        reject(new Error("카카오맵 SDK 초기화 실패 (키 또는 도메인 설정 확인)"));
        return;
      }
      kakao.maps.load(() => resolve());
    };
    if (existing) {
      existing.addEventListener("load", onLoad);
      return;
    }
    const script = document.createElement("script");
    script.id = SDK_ID;
    script.async = true;
    script.src = `//dapi.kakao.com/v2/maps/sdk.js?appkey=${appKey}&autoload=false`;
    script.onload = onLoad;
    script.onerror = () => reject(new Error("카카오맵 SDK 로드 실패 (키 또는 도메인 설정 확인)"));
    document.head.appendChild(script);
  });
}

function markerImage(kakao: KakaoNamespace, selected: boolean) {
  const width = selected ? 38 : 30;
  const height = selected ? 48 : 40;
  const fill = selected ? "#e24b35" : "#3367d6";
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 38 48"><path d="M19 2C9.6 2 2 9.5 2 18.8 2 31 19 46 19 46s17-15 17-27.2C36 9.5 28.4 2 19 2Z" fill="${fill}" stroke="white" stroke-width="3"/><circle cx="19" cy="19" r="6" fill="white"/></svg>`;
  const image = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  return new kakao.maps.MarkerImage(
    image,
    new kakao.maps.Size(width, height),
    { offset: new kakao.maps.Point(width / 2, height) },
  );
}

type Props = {
  places: Place[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  appKey: string;
  // Mobile only: area not covered by header/sheet. null on desktop and when the sheet is expanded.
  mapInsets: MapInsets | null;
  // Mobile only: panel mode, changes only on release (not during drag). null on desktop.
  layoutKey: string | null;
};

// Places the coordinate so that it sits at the center of the visible (inset) area.
function centerPlace(
  map: KakaoMapInstance,
  kakao: KakaoNamespace,
  container: HTMLElement | null,
  place: Place,
  insets: MapInsets | null,
) {
  const target = new kakao.maps.LatLng(place.lat, place.lng);
  if (!insets || !container) {
    map.panTo(target);
    return;
  }
  const width = container.clientWidth;
  const height = container.clientHeight;
  const projection = map.getProjection();
  const current = projection.containerPointFromCoords(target);
  const desiredX = (insets.left + (width - insets.right)) / 2;
  const desiredY = (insets.top + (height - insets.bottom)) / 2;
  const dx = desiredX - current.x;
  const dy = desiredY - current.y;
  // The coordinate currently at (center - delta) becomes the new center after the marker shifts by delta.
  const center = projection.coordsFromContainerPoint(
    new kakao.maps.Point(width / 2 - dx, height / 2 - dy),
  );
  map.panTo(center);
}

function fitPlaces(map: KakaoMapInstance, kakao: KakaoNamespace, places: Place[], insets: MapInsets | null) {
  const bounds = new kakao.maps.LatLngBounds();
  for (const place of places) bounds.extend(new kakao.maps.LatLng(place.lat, place.lng));
  if (!insets) map.setBounds(bounds);
  else map.setBounds(bounds, insets.top, insets.right, insets.bottom, insets.left);
}

export default function KakaoMap({ places, selectedId, onSelect, appKey, mapInsets, layoutKey }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<KakaoMapInstance | null>(null);
  const overlayRef = useRef<KakaoOverlay | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [overlayHost, setOverlayHost] = useState<HTMLDivElement | null>(null);
  const markersRef = useRef<Map<string, KakaoMarker>>(new Map());
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const selectedPlace = selectedId ? places.find((place) => place.id === selectedId) ?? null : null;
  const insetsRef = useRef<MapInsets | null>(mapInsets);
  insetsRef.current = mapInsets;
  const placesRef = useRef(places);
  placesRef.current = places;
  const selectedPlaceRef = useRef(selectedPlace);
  selectedPlaceRef.current = selectedPlace;

  useEffect(() => {
    if (!selectedPlace) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onSelect(null);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [selectedPlace, onSelect]);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 800px)");
    const update = () => setIsMobile(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    let cancelled = false;
    loadKakaoSdk(appKey)
      .then(() => {
        if (cancelled || !containerRef.current) return;
        const kakao = window.kakao;
        if (!kakao?.maps) throw new Error("카카오맵 SDK 초기화 실패");
        mapRef.current = new kakao.maps.Map(containerRef.current, {
          center: new kakao.maps.LatLng(SEOUL_CENTER.lat, SEOUL_CENTER.lng),
          level: 7,
        });
        setMapReady(true);
      })
      .catch((err: Error) => {
        if (containerRef.current) containerRef.current.textContent = err.message;
      });
    return () => {
      cancelled = true;
    };
  }, [appKey]);

  useEffect(() => {
    const map = mapRef.current;
    const container = containerRef.current;
    if (!mapReady || !map || !container || typeof ResizeObserver === "undefined") return;
    let frame = 0;
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => map.relayout());
    });
    observer.observe(container);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    const kakao = window.kakao;
    if (!mapReady || !map || !kakao?.maps) return;

    const hasSamePlaces = markersRef.current.size === places.length
      && places.every((place) => markersRef.current.has(place.id));
    if (hasSamePlaces) return;

    markersRef.current.forEach((marker) => marker.setMap(null));
    markersRef.current = new Map();

    for (const place of places) {
      const position = new kakao.maps.LatLng(place.lat, place.lng);
      const marker = new kakao.maps.Marker({
        position,
        title: place.name,
        image: markerImage(kakao, place.id === selectedId),
        zIndex: place.id === selectedId ? 10 : 1,
      });
      marker.setMap(map);
      kakao.maps.event.addListener(marker, "click", () => onSelectRef.current(place.id));
      markersRef.current.set(place.id, marker);
    }
    if (places.length > 0) fitPlaces(map, kakao, places, insetsRef.current);
  }, [places, mapReady, selectedId]);

  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map || !window.kakao?.maps) return;
    const { kakao } = window;
    markersRef.current.forEach((marker, id) => {
      const selected = id === selectedId;
      marker.setImage(markerImage(kakao, selected));
      marker.setZIndex(selected ? 10 : 1);
    });
    if (selectedPlace) {
      centerPlace(map, kakao, containerRef.current, selectedPlace, insetsRef.current);
    }
  }, [selectedId, selectedPlace, mapReady]);

  // Panel mode changed (not during drag): refit the visible area, or re-center the selected pin.
  useEffect(() => {
    const map = mapRef.current;
    const kakao = window.kakao;
    if (!mapReady || !map || !kakao?.maps || layoutKey === null || layoutKey === "expanded") return;
    const selected = selectedPlaceRef.current;
    if (selected) centerPlace(map, kakao, containerRef.current, selected, insetsRef.current);
    else if (placesRef.current.length > 0) fitPlaces(map, kakao, placesRef.current, insetsRef.current);
  }, [layoutKey, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (overlayRef.current) {
      overlayRef.current.setMap(null);
      overlayRef.current = null;
    }
    setOverlayHost(null);
    if (!mapReady || !map || !selectedPlace || isMobile || !window.kakao?.maps) return;

    const kakao = window.kakao;
    const host = document.createElement("div");
    host.className = "map-bubble-host";
    const overlay = new kakao.maps.CustomOverlay({
      position: new kakao.maps.LatLng(selectedPlace.lat, selectedPlace.lng),
      content: host,
      xAnchor: 0.5,
      yAnchor: 1.0,
      zIndex: 20,
      clickable: true,
    });
    overlay.setMap(map);
    overlayRef.current = overlay;
    setOverlayHost(host);

    return () => {
      overlay.setMap(null);
      if (overlayRef.current === overlay) overlayRef.current = null;
    };
  }, [mapReady, selectedPlace, isMobile]);

  return (
    <>
      <div ref={containerRef} className="map" />
      {!isMobile && overlayHost && selectedPlace && createPortal(
        <PlaceDetail place={selectedPlace} onClose={() => onSelect(null)} />,
        overlayHost,
      )}
    </>
  );
}
