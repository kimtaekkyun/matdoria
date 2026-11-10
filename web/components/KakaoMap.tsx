"use client";

import { useEffect, useRef, useState } from "react";
import type { Place } from "../lib/types";

declare global {
  interface Window {
    kakao: any; // 카카오 지도 SDK 전역 객체 (타입 정의 없음)
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

type Props = {
  places: Place[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  appKey: string;
};

export default function KakaoMap({ places, selectedId, onSelect, appKey }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  // 지도 객체가 만들어졌는지 상태로 둔다. ref만 쓰면 마커 effect가 지도 생성 뒤에 다시 실행되지 않는다.
  const [mapReady, setMapReady] = useState(false);
  const markersRef = useRef<Map<string, any>>(new Map());
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  // 지도 초기화 (한 번)
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
        if (containerRef.current) {
          containerRef.current.textContent = err.message;
        }
      });
    return () => {
      cancelled = true;
    };
  }, [appKey]);

  // 마커 갱신 (필터가 바뀔 때)
  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map || !window.kakao?.maps) return;
    const { kakao } = window;

    markersRef.current.forEach((m) => m.setMap(null));
    markersRef.current = new Map();

    const bounds = new kakao.maps.LatLngBounds();
    for (const place of places) {
      const position = new kakao.maps.LatLng(place.lat, place.lng);
      const marker = new kakao.maps.Marker({ position, title: place.name });
      marker.setMap(map);
      kakao.maps.event.addListener(marker, "click", () => onSelectRef.current(place.id));
      markersRef.current.set(place.id, marker);
      bounds.extend(position);
    }
    if (places.length > 0) {
      map.setBounds(bounds);
    }
  }, [places, mapReady]);

  // 선택 변경 시 지도 이동
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !selectedId || !window.kakao?.maps) return;
    const place = places.find((p) => p.id === selectedId);
    if (!place) return;
    map.panTo(new window.kakao.maps.LatLng(place.lat, place.lng));
  }, [selectedId, places]);

  return <div ref={containerRef} className="map" />;
}
