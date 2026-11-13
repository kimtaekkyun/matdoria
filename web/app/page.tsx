"use client";

import { useMemo, useRef, useState } from "react";
import type { PointerEvent } from "react";
import dynamic from "next/dynamic";
import placesData from "../public/data/places.json";
import type { Place } from "../lib/types";
import { SOURCE_FILTERS, SOURCE_STATUS, matchesFilter, type SourceFilter } from "../lib/sources";
import PlaceDetail from "../components/PlaceDetail";

// 지도는 브라우저에서만 동작하므로 SSR을 끈다.
const KakaoMap = dynamic(() => import("../components/KakaoMap"), {
  ssr: false,
  loading: () => <div className="map" />,
});

const places = placesData as Place[];
const KAKAO_MAP_KEY = process.env.NEXT_PUBLIC_KAKAO_MAP_KEY ?? "";

const SORT_OPTIONS = [
  { key: "name", label: "이름순" },
  { key: "kakao_rating", label: "K Star 높은 순" },
  { key: "kakao_count", label: "K 리뷰 많은 순" },
  { key: "google_rating", label: "G Star 높은 순" },
  { key: "google_count", label: "G 평가 많은 순" },
] as const;
type SortKey = (typeof SORT_OPTIONS)[number]["key"];

function ListRating({ label, rating, count }: { label: "K Star" | "G Star"; rating: number | null; count: number | null }) {
  const fill = rating === null ? 0 : Math.max(0, Math.min(100, (rating / 5) * 100));
  const style = { backgroundImage: `linear-gradient(90deg, #e5a100 ${fill}%, #d5d7dc ${fill}%)` };
  return (
    <span className="list-rating">
      <span className="list-rating-label">{label}</span>
      <span className="list-rating-score">{rating === null ? "" : rating.toFixed(1)}</span>
      <span className="rating-stars list-rating-stars" style={style} aria-label={rating === null ? "평점 없음" : `${fill.toFixed(0)}% 별점`}>★★★★★</span>
      <span className="list-rating-count">{rating === null || count === null ? "" : `(${count.toLocaleString("ko-KR")})`}</span>
    </span>
  );
}

export default function Home() {
  const [filter, setFilter] = useState<SourceFilter>("all");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<SortKey>("name");
  const [listExpanded, setListExpanded] = useState(false);
  const pointerStartY = useRef<number | null>(null);
  const suppressToggleClickUntil = useRef(0);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = places.filter(
      (p) =>
        matchesFilter(p.sources, filter, p.matdoriaPick?.selected === true) &&
        (q === "" || p.name.toLowerCase().includes(q) || p.address.includes(q)),
    );
    const metric = (place: Place): number | null => {
      switch (sortBy) {
        case "kakao_rating": return place.ratings?.kakao?.rating ?? null;
        case "kakao_count": return place.ratings?.kakao?.count ?? null;
        case "google_rating": return place.ratings?.google?.rating ?? null;
        case "google_count": return place.ratings?.google?.count ?? null;
        default: return null;
      }
    };
    return filtered.sort((a, b) => {
      if (sortBy === "name") return a.name.localeCompare(b.name, "ko");
      const av = metric(a);
      const bv = metric(b);
      if (av === null && bv !== null) return 1;
      if (av !== null && bv === null) return -1;
      if (av !== null && bv !== null && av !== bv) return bv - av;
      return a.name.localeCompare(b.name, "ko");
    });
  }, [filter, query, sortBy]);

  const selected = selectedId ? visible.find((place) => place.id === selectedId) ?? null : null;

  const sourceCounts = useMemo(() => {
    return Object.fromEntries(
      SOURCE_FILTERS.map(({ key }) => [
        key,
        key === "all"
          ? places.length
          : places.filter((place) => matchesFilter(place.sources, key, place.matdoriaPick?.selected === true)).length,
      ]),
    ) as Record<SourceFilter, number>;
  }, []);

  const onPanelPointerDown = (event: PointerEvent<HTMLButtonElement>) => {
    pointerStartY.current = event.clientY;
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const onPanelPointerUp = (event: PointerEvent<HTMLButtonElement>) => {
    if (pointerStartY.current === null) return;
    const deltaY = event.clientY - pointerStartY.current;
    pointerStartY.current = null;
    if (Math.abs(deltaY) > 24) {
      setListExpanded(deltaY < 0);
      suppressToggleClickUntil.current = Date.now() + 500;
    }
  };
  const onPanelToggleClick = () => {
    if (Date.now() < suppressToggleClickUntil.current) return;
    setListExpanded((expanded) => !expanded);
  };

  return (
    <div className={`app${listExpanded ? " list-expanded" : ""}`}>
      <aside className={`sidebar${selected ? " has-selection" : ""}`}>
        <button
          type="button"
          className="mobile-panel-toggle"
          aria-label={listExpanded ? "리스트 패널 접기" : "리스트 전체 화면으로 펼치기"}
          aria-expanded={listExpanded}
          onPointerDown={onPanelPointerDown}
          onPointerUp={onPanelPointerUp}
          onPointerCancel={() => { pointerStartY.current = null; }}
          onClick={onPanelToggleClick}
        >
          <span />
        </button>
        <div className="sidebar-head">
          <h1>matdoria · 서울</h1>
          <input
            className="search"
            placeholder="식당 이름 또는 주소 검색"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="chips" role="tablist" aria-label="맛집 출처별 목록">
            {SOURCE_FILTERS.map((f) => (
              <button
                key={f.key}
                className="chip"
                role="tab"
                aria-selected={filter === f.key}
                onClick={() => setFilter(f.key)}
              >
                {f.label}
                <span className="chip-count">{sourceCounts[f.key]}</span>
              </button>
            ))}
          </div>
          <div className="list-toolbar">
            <div className="count">{visible.length}곳 표시 · 전체 {places.length}곳</div>
            <select className="sort-select" value={sortBy} onChange={(e) => setSortBy(e.target.value as SortKey)} aria-label="정렬 기준">
              {SORT_OPTIONS.map((option) => <option key={option.key} value={option.key}>{option.label}</option>)}
            </select>
          </div>
        </div>

        <div className={`sidebar-content${selected ? " has-selection" : ""}`}>
          {selected && (
            <div className="mobile-detail-pane">
              <PlaceDetail place={selected} onClose={() => setSelectedId(null)} presentation="inline" />
            </div>
          )}
          {visible.length === 0 ? (
            <div className="empty">
              {query.trim()
                ? "검색 조건에 맞는 식당이 없습니다."
                : sourceCounts[filter] === 0
                  ? SOURCE_STATUS[filter]
                  : "조건에 맞는 식당이 없습니다."}
            </div>
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
                    {[
                      ...p.sources.map((source) => SOURCE_FILTERS.find((f) => f.key === source.source)?.label),
                      ...(p.matdoriaPick?.selected ? ["Matdoria's Pick"] : []),
                    ].filter(Boolean).join(" · ")}
                    {" · "}
                    {p.address}
                  </div>
                  <div className="list-item-ratings">
                    <ListRating label="K Star" rating={p.ratings?.kakao?.rating ?? null} count={p.ratings?.kakao?.count ?? null} />
                    <ListRating label="G Star" rating={p.ratings?.google?.rating ?? null} count={p.ratings?.google?.count ?? null} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="notice">
          장소 정보는 카카오 로컬 기준입니다. 출처별 데이터는 공식 수집 경로와 식당 매칭이 확인된 뒤 차례로 추가합니다. Matdoria's Pick은 별도 큐레이션 기준으로 구성합니다.
        </div>
      </aside>

      <main className="map-wrap">
        <KakaoMap
          places={visible}
          selectedId={selectedId}
          onSelect={setSelectedId}
          appKey={KAKAO_MAP_KEY}
        />
        {!KAKAO_MAP_KEY && (
          <div className="detail" style={{ top: "auto", bottom: 16, left: 16, right: "auto", width: 300 }}>
            카카오 JavaScript 키가 없습니다. web/.env.local 에 NEXT_PUBLIC_KAKAO_MAP_KEY 를 넣어 주세요.
          </div>
        )}
      </main>
    </div>
  );
}
