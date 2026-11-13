"use client";

import { createPortal } from "react-dom";
import { useEffect, useRef, useState } from "react";
import type { Place } from "../lib/types";
import PlaceDetail from "./PlaceDetail";

declare global {
  interface Window {
    kakao: any; // Kakao Maps SDK does not expose bundled TypeScript definitions.
  }
}

const SEOUL_CENTER = { lat: 37.5665, lng: 126.978 };
const SDK_ID = "kakao-map-sdk";

function loadKakaoSdk(appKey: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if (window.kakao?.maps) {
      window.kakao.maps.load(() => resolve());
      return;
    }
    const existing = document.getElementById(SDK_ID) as HTMLScriptElement | null;
    const onLoad = () => window.kakao.maps.load(() => resolve());
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

function markerImage(kakao: any, selected: boolean) {
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
};

export default function KakaoMap({ places, selectedId, onSelect, appKey }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const overlayRef = useRef<any>(null);
  const [mapReady, setMapReady] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [overlayHost, setOverlayHost] = useState<HTMLDivElement | null>(null);
  const markersRef = useRef<Map<string, any>>(new Map());
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const selectedPlace = selectedId ? places.find((place) => place.id === selectedId) ?? null : null;

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
        const { kakao } = window;
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
    if (!mapReady || !map || !window.kakao?.maps) return;
    const { kakao } = window;

    markersRef.current.forEach((marker) => marker.setMap(null));
    markersRef.current = new Map();

    const bounds = new kakao.maps.LatLngBounds();
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
      bounds.extend(position);
    }
    if (places.length > 0) map.setBounds(bounds);
  }, [places, mapReady]);

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
      map.panTo(new kakao.maps.LatLng(selectedPlace.lat, selectedPlace.lng));
    }
  }, [selectedId, selectedPlace, mapReady]);

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
