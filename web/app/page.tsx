"use client";

import { useMemo, useState } from "react";
import dynamic from "next/dynamic";
import placesData from "../public/data/places.json";
import type { Place } from "../lib/types";
import { SOURCE_FILTERS, matchesFilter, type SourceFilter } from "../lib/sources";
import PlaceDetail from "../components/PlaceDetail";

// 지도는 브라우저에서만 동작하므로 SSR을 끈다.
const KakaoMap = dynamic(() => import("../components/KakaoMap"), {
  ssr: false,
  loading: () => <div className="map" />,
});

const places = placesData as Place[];
const KAKAO_MAP_KEY = process.env.NEXT_PUBLIC_KAKAO_MAP_KEY ?? "";

export default function Home() {
  const [filter, setFilter] = useState<SourceFilter>("all");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return places.filter(
      (p) =>
        matchesFilter(p.sources, filter) &&
        (q === "" || p.name.toLowerCase().includes(q) || p.address.includes(q)),
    );
  }, [filter, query]);

  const selected = selectedId ? visible.find((p) => p.id === selectedId) ?? null : null;

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sidebar-head">
          <h1>matdoria · 서울</h1>
          <input
            className="search"
            placeholder="식당 이름 또는 주소 검색"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="chips" role="group" aria-label="출처 필터">
            {SOURCE_FILTERS.map((f) => (
              <button
                key={f.key}
                className="chip"
                aria-pressed={filter === f.key}
                onClick={() => setFilter(f.key)}
              >
                {f.label}
              </button>
            ))}
          </div>
          <div className="count">{visible.length}곳 표시 (전체 {places.length}곳)</div>
        </div>

        {visible.length === 0 ? (
          <div className="empty">조건에 맞는 식당이 없습니다.</div>
        ) : (
          <ul className="list">
            {visible.map((p) => (
              <li
                key={p.id}
                className="list-item"
                aria-selected={p.id === selectedId}
                onClick={() => setSelectedId(p.id)}
              >
                <div className="list-item-name">{p.name}</div>
                <div className="list-item-sub">
                  {p.sources.map((s) => (s.source === "michelin" ? "미쉐린" : "서울미래유산")).join(" · ")}
                  {" · "}
                  {p.address}
                </div>
              </li>
            ))}
          </ul>
        )}

        <div className="notice">
          장소 정보는 카카오 로컬 기준입니다. 미쉐린과 서울미래유산 정보는 공개 자료를 자동 매칭한 결과이므로 실제와 다를 수 있습니다.
        </div>
      </aside>

      <main className="map-wrap">
        <KakaoMap
          places={visible}
          selectedId={selectedId}
          onSelect={setSelectedId}
          appKey={KAKAO_MAP_KEY}
        />
        {selected && <PlaceDetail place={selected} onClose={() => setSelectedId(null)} />}
        {!KAKAO_MAP_KEY && (
          <div className="detail" style={{ top: "auto", bottom: 16, left: 16, right: "auto", width: 300 }}>
            카카오 JavaScript 키가 없습니다. web/.env.local 에 NEXT_PUBLIC_KAKAO_MAP_KEY 를 넣어 주세요.
          </div>
        )}
      </main>
    </div>
  );
}
