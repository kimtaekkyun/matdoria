"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, KeyboardEvent, PointerEvent, WheelEvent } from "react";
import dynamic from "next/dynamic";
import placesData from "../public/data/places.json";
import buildInfo from "../public/data/build-info.json";
import { meetsPickReviewThresholds } from "../lib/types";
import type { Place } from "../lib/types";
import { CURATION_FILTERS, SOURCE_FILTERS, SOURCE_STATUS, matchesFilter, type CurationFilter, type ListFilter, type SourceFilter } from "../lib/sources";
import PlaceDetail from "../components/PlaceDetail";
import TrustPanel from "../components/TrustPanel";
import { nearestPanelMode, sheetTop, useMobileLayout, visibleInsets, type PanelMode } from "../lib/mobileLayout";

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
  { key: "kakao_count", label: "K Review 수 많은 순" },
  { key: "google_rating", label: "G Star 높은 순" },
  { key: "google_count", label: "G Review 수 많은 순" },
] as const;
type SortKey = (typeof SORT_OPTIONS)[number]["key"];
type PanelDrag = { startY: number; startTop: number; lastTop: number; moved: boolean };

function ListRating({ label, rating, count }: { label: "K Star" | "G Star"; rating: number | null; count: number | null }) {
  const fill = rating === null ? 0 : Math.max(0, Math.min(100, (rating / 5) * 100));
  const style = { backgroundImage: `linear-gradient(90deg, #e5a100 ${fill}%, #d5d7dc ${fill}%)` };
  return (
    <span className="list-rating">
      <span className="list-rating-label">{label}</span>
      <span className="list-rating-score">{rating === null ? "—" : rating.toFixed(1)}</span>
      <span className="rating-stars list-rating-stars" role="img" style={style} aria-label={rating === null ? `${label} 정보 없음` : `${label} ${rating.toFixed(1)}점`}>★★★★★</span>
      <span className="list-rating-count">{count === null ? "" : `(${count.toLocaleString("ko-KR")})`}</span>
    </span>
  );
}

export default function Home() {
  const [filter, setFilter] = useState<ListFilter>("matdoria_pick");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [activeOptionId, setActiveOptionId] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<SortKey>("google_count");
  const [panelMode, setPanelMode] = useState<PanelMode>("split");
  const [isPanelDragging, setIsPanelDragging] = useState(false);
  const [sourceMenuOpen, setSourceMenuOpen] = useState(false);
  const appRef = useRef<HTMLDivElement>(null);
  const headRef = useRef<HTMLDivElement>(null);
  const sourceRef = useRef<HTMLDivElement>(null);
  const sourceTriggerRef = useRef<HTMLButtonElement>(null);
  const panelDrag = useRef<PanelDrag | null>(null);
  const suppressToggleClickUntil = useRef(0);
  const layout = useMobileLayout(appRef, headRef);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = places.filter(
      (p) =>
        matchesFilter(p.sources, filter, meetsPickReviewThresholds(p)) &&
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

  useEffect(() => {
    if (selectedId && !visible.some((place) => place.id === selectedId)) {
      setSelectedId(null);
    }
  }, [selectedId, visible]);

  const selected = selectedId ? visible.find((place) => place.id === selectedId) ?? null : null;
  const focusedOptionId = visible.some((place) => place.id === activeOptionId)
    ? activeOptionId
    : selected?.id ?? visible[0]?.id ?? null;

  const sourceCounts = useMemo(() => {
    return Object.fromEntries(
      SOURCE_FILTERS.map(({ key }) => [
        key,
        key === "all"
          ? places.length
          : places.filter((place) => matchesFilter(place.sources, key, meetsPickReviewThresholds(place))).length,
      ]),
    ) as Record<SourceFilter, number>;
  }, []);

  const curationCounts = useMemo(() => Object.fromEntries(
    CURATION_FILTERS.map(({ key }) => [
      key,
      places.filter((place) => matchesFilter(place.sources, key, meetsPickReviewThresholds(place))).length,
    ]),
  ) as Record<CurationFilter, number>, []);
  const activeFilterCount = filter === "matdoria_pick" ? curationCounts[filter] : sourceCounts[filter];

  const clampPanelTop = (top: number) => {
    if (!layout) return top;
    return Math.max(sheetTop("expanded", layout), Math.min(sheetTop("peek", layout), top));
  };
  const onPanelPointerDown = (event: PointerEvent<HTMLButtonElement>) => {
    const sidebar = appRef.current?.querySelector(".sidebar");
    if (!sidebar || !layout) return;
    // A drag moves the sheet under the popover, so close the menu rather than leave it stale.
    setSourceMenuOpen(false);
    const startTop = sidebar.getBoundingClientRect().top;
    panelDrag.current = { startY: event.clientY, startTop, lastTop: startTop, moved: false };
    appRef.current?.style.setProperty("--panel-top", `${startTop}px`);
    setIsPanelDragging(true);
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const onPanelPointerMove = (event: PointerEvent<HTMLButtonElement>) => {
    const drag = panelDrag.current;
    if (!drag || !appRef.current) return;
    const nextTop = clampPanelTop(drag.startTop + event.clientY - drag.startY);
    drag.lastTop = nextTop;
    drag.moved ||= Math.abs(event.clientY - drag.startY) > 8;
    appRef.current.style.setProperty("--panel-top", `${nextTop}px`);
  };
  const finishPanelDrag = (event?: PointerEvent<HTMLButtonElement>) => {
    const drag = panelDrag.current;
    if (!drag) return;
    const top = event ? clampPanelTop(drag.startTop + event.clientY - drag.startY) : drag.lastTop;
    const moved = drag.moved || (event ? Math.abs(event.clientY - drag.startY) > 8 : false);
    if (moved) {
      if (layout) setPanelMode(nearestPanelMode(top, layout));
      suppressToggleClickUntil.current = Date.now() + 500;
    }
    panelDrag.current = null;
    setIsPanelDragging(false);
  };
  const movePanel = (direction: "up" | "down") => {
    setPanelMode((mode) => {
      if (direction === "up") return mode === "peek" ? "split" : "expanded";
      return mode === "expanded" ? "split" : "peek";
    });
  };
  const selectPlace = (id: string | null) => {
    setSelectedId(id);
    // Picking a pin or row from the peek bar opens the lower detail sheet, keeping the map visible.
    if (id && panelMode === "peek") setPanelMode("split");
  };
  const onPlaceKeyDown = (event: KeyboardEvent<HTMLLIElement>, id: string) => {
    const options = Array.from(
      event.currentTarget.parentElement?.querySelectorAll<HTMLElement>('[role="option"]') ?? [],
    );
    const index = options.indexOf(event.currentTarget);
    let nextIndex: number | null = null;
    if (event.key === "ArrowDown") nextIndex = Math.min(index + 1, options.length - 1);
    if (event.key === "ArrowUp") nextIndex = Math.max(index - 1, 0);
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = options.length - 1;
    if (nextIndex !== null) {
      event.preventDefault();
      options[nextIndex]?.focus();
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      selectPlace(id);
    }
  };
  const onPanelPointerUp = (event: PointerEvent<HTMLButtonElement>) => finishPanelDrag(event);
  const onPanelToggleClick = () => {
    if (Date.now() < suppressToggleClickUntil.current) return;
    setPanelMode((mode) => mode === "peek" ? "split" : mode === "split" ? "expanded" : "split");
  };
  const onPanelWheel = (event: WheelEvent<HTMLElement>) => {
    if (!layout || Math.abs(event.deltaY) < 12) return;
    const target = event.target as HTMLElement;
    const onHandle = target.closest(".mobile-panel-toggle");
    if (onHandle) {
      movePanel(event.deltaY < 0 ? "up" : "down");
      return;
    }
    if (target.closest("input, select, button, a")) return;

    const detail = target.closest(".detail-scroll") as HTMLElement | null;
    if (detail?.closest(".detail-inline")) {
      if (panelMode === "split" && event.deltaY < 0 && detail.scrollTop <= 0) setPanelMode("expanded");
      return;
    }
    const list = target.closest(".list") as HTMLElement | null;
    if (list && panelMode === "split" && event.deltaY < 0 && list.scrollTop <= 0) setPanelMode("expanded");
  };

  useEffect(() => {
    if (!sourceMenuOpen) return;
    const onPointerDown = (event: globalThis.PointerEvent) => {
      if (!sourceRef.current?.contains(event.target as Node)) setSourceMenuOpen(false);
    };
    // Capture phase + stopImmediatePropagation so Escape closes only the menu, not the open detail.
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.stopImmediatePropagation();
      setSourceMenuOpen(false);
      sourceTriggerRef.current?.focus();
    };
    document.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown, true);
    };
  }, [sourceMenuOpen]);

  // Any change of panel mode (handle, wheel, drag, peek) closes the source menu so it never covers a moved sheet.
  useEffect(() => {
    setSourceMenuOpen(false);
  }, [panelMode]);

  const sourceTriggerLabel = filter === "matdoria_pick"
    ? "출처"
    : `출처 · ${SOURCE_FILTERS.find((f) => f.key === filter)?.label ?? ""}`;
  const appStyle = layout
    ? ({
        "--split-top": `${sheetTop("split", layout)}px`,
        "--peek-top": `${sheetTop("peek", layout)}px`,
        "--expanded-top": `${sheetTop("expanded", layout)}px`,
        "--header-bottom": `${layout.headerBottom}px`,
      } as CSSProperties)
    : undefined;
  const mapInsets = layout ? visibleInsets(panelMode, layout) : null;

  return (
    <div ref={appRef} className={`app panel-${panelMode}${isPanelDragging ? " panel-dragging" : ""}`} style={appStyle}>
      <aside className={`sidebar${selected ? " has-selection" : ""}${panelMode === "peek" ? " panel-peek" : ""}`} onWheel={onPanelWheel}>
        <button
          type="button"
          className="mobile-panel-toggle"
          aria-label={panelMode === "expanded" ? "현재 리스트 전체 화면. 분할 화면으로 접기" : panelMode === "split" ? "현재 지도와 목록 분할 화면. 리스트 전체 화면으로 펼치기" : "현재 지도 크게 보기. 리스트 보기"}
          onPointerDown={onPanelPointerDown}
          onPointerMove={onPanelPointerMove}
          onPointerUp={onPanelPointerUp}
          onPointerCancel={() => finishPanelDrag()}
          onClick={onPanelToggleClick}
        >
          <span />
        </button>
        {panelMode === "peek" && (
          <button
            type="button"
            className="mobile-map-peek"
            onClick={() => setPanelMode("split")}
            aria-label={selected ? `${selected.name} 상세 열기` : `목록 보기, ${visible.length}곳`}
          >
            <span>{selected ? selected.name : `${visible.length}곳 · 목록 보기`}</span><span aria-hidden="true">↑</span>
          </button>
        )}
        <div className="sidebar-head" ref={headRef}>
          <h1>matdoria · 서울</h1>
          <div className="curation-section" role="group" aria-label="Matdoria 큐레이션 목록">
            <div className="section-heading">Matdoria 큐레이션</div>
            {CURATION_FILTERS.map((curation) => (
              <button
                key={curation.key}
                type="button"
                className={`curation-card${filter === curation.key ? " is-active" : ""}`}
                aria-pressed={filter === curation.key}
                onClick={() => {
                  setFilter(curation.key);
                  setSortBy("google_count");
                }}
              >
                <span className="curation-card-copy">
                  <strong>{curation.label}</strong>
                </span>
                <span className="curation-count">{curationCounts[curation.key]}</span>
              </button>
            ))}
          </div>
          <TrustPanel />
          <input
            className="search"
            aria-label="식당 이름 또는 주소 검색"
            placeholder="식당 이름 또는 주소 검색"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className={`source-section${sourceMenuOpen ? " is-open" : ""}`} ref={sourceRef}>
            <div className="source-section-heading">
              <span>출처별 보기</span>
              <span className="source-scroll-hint">옆으로 밀어 더 보기 <span aria-hidden="true">→</span></span>
            </div>
            <button
              ref={sourceTriggerRef}
              type="button"
              className="source-trigger"
              aria-expanded={sourceMenuOpen}
              aria-controls="source-menu"
              onClick={() => setSourceMenuOpen((open) => !open)}
            >
              <span>{sourceTriggerLabel}</span>
              <span aria-hidden="true">▾</span>
            </button>
            <div className="chips" id="source-menu" role="group" aria-label="출처별 목록">
              {SOURCE_FILTERS.map((f) => (
                <button
                  key={f.key}
                  type="button"
                  className="chip"
                  aria-pressed={filter === f.key}
                  onClick={() => {
                    setFilter(f.key);
                    setSourceMenuOpen(false);
                  }}
                >
                  {f.label}
                  <span className="chip-count">{sourceCounts[f.key]}</span>
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="list-toolbar">
          <div className="count">{visible.length}곳 표시 · 전체 {places.length}곳</div>
          <select className="sort-select" value={sortBy} onChange={(e) => setSortBy(e.target.value as SortKey)} aria-label="정렬 기준">
            {SORT_OPTIONS.map((option) => <option key={option.key} value={option.key}>{option.label}</option>)}
          </select>
        </div>

        <div className={`sidebar-content${selected ? " has-selection" : ""}`}>
          {selected && (
            <div className="mobile-detail-pane">
              <PlaceDetail key={selected.id} place={selected} onClose={() => selectPlace(null)} presentation="inline" />
            </div>
          )}
          {visible.length === 0 ? (
            <div className="empty">
              {query.trim()
                ? "검색 조건에 맞는 식당이 없습니다."
                : activeFilterCount === 0
                  ? filter === "matdoria_pick"
                    ? `K Review ${buildInfo.reviewCountThresholds.kakaoReviewCount}개 · K Star ${buildInfo.ratingThresholds.kakaoRating.toFixed(1)}점 · G Review ${buildInfo.reviewCountThresholds.googleUserRatingCount}개 · G Star ${buildInfo.ratingThresholds.googleRating.toFixed(1)}점 기준을 모두 충족한 장소가 없습니다.`
                    : SOURCE_STATUS[filter]
                  : "조건에 맞는 식당이 없습니다."}
            </div>
          ) : (
            <ul className="list" role="listbox" aria-label="식당 목록">
              {visible.map((p) => (
                <li
                  key={p.id}
                  className="list-item"
                  role="option"
                  aria-selected={p.id === selectedId}
                  tabIndex={focusedOptionId === p.id ? 0 : -1}
                  onClick={() => selectPlace(p.id)}
                  onFocus={() => setActiveOptionId(p.id)}
                  onKeyDown={(event) => onPlaceKeyDown(event, p.id)}
                >
                  <div className="list-item-name">{p.name}</div>
                  <div className="list-item-sub">
                    <span className="list-item-sources">
                      {[
                        ...p.sources.map((source) => SOURCE_FILTERS.find((f) => f.key === source.source)?.label),
                        ...(meetsPickReviewThresholds(p) ? ["Matdoria's Pick"] : []),
                      ].filter(Boolean).join(" · ")}
                    </span>
                    <span className="list-item-address">{p.address}</span>
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
          장소 정보는 카카오 로컬 기준입니다. Matdoria&apos;s Pick 선정 기준은 상단 안내에서 확인할 수 있습니다.
        </div>
      </aside>

      <main className="map-wrap">
        <KakaoMap
          places={visible}
          selectedId={selectedId}
          onSelect={selectPlace}
          appKey={KAKAO_MAP_KEY}
          mapInsets={mapInsets}
          layoutKey={layout ? panelMode : null}
        />
        {!KAKAO_MAP_KEY && (
          <div className="detail" style={{ top: "auto", bottom: 16, left: 16, right: "auto", width: 300, padding: 20 }}>
            카카오 JavaScript 키가 없습니다. web/.env.local 에 NEXT_PUBLIC_KAKAO_MAP_KEY 를 넣어 주세요.
          </div>
        )}
      </main>
    </div>
  );
}
