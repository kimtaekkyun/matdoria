import type { Place, PlaceSource, RatingSnapshot } from "../lib/types";
import { SOURCE_FILTERS, awardText } from "../lib/sources";

type RatingLineProps = { prefix: "K Star" | "G Star"; result: RatingSnapshot | null; showCollectedDate?: boolean };

function RatingLine({ prefix, result, showCollectedDate = false }: RatingLineProps) {
  const rating = result?.rating ?? null;
  const collectedAt = showCollectedDate && result?.collectedAt ? new Date(result.collectedAt) : null;
  const collectedDate = collectedAt && !Number.isNaN(collectedAt.getTime())
    ? new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium", timeZone: "Asia/Seoul" }).format(collectedAt)
    : null;
  const fill = rating === null ? 0 : Math.max(0, Math.min(100, (rating / 5) * 100));
  const starsStyle = { backgroundImage: `linear-gradient(90deg, #e5a100 ${fill}%, #d5d7dc ${fill}%)` };

  return (
    <div className="rating-row">
      <strong className="rating-prefix">{prefix}</strong>
      <span className="rating-number">{rating === null ? "—" : rating.toFixed(1)}</span>
      <span className="rating-stars" role="img" style={starsStyle} aria-label={rating === null ? `${prefix} 정보 없음` : `${prefix} ${rating.toFixed(1)}점`}>★★★★★</span>
      <span className="rating-count">{rating === null || result?.count == null ? "" : `(${result.count.toLocaleString("ko-KR")})`}</span>
      {collectedDate && <time className="rating-collected-at" dateTime={result?.collectedAt ?? undefined}>수집 {collectedDate}</time>}
    </div>
  );
}

function sourceLabel(source: PlaceSource): string {
  return SOURCE_FILTERS.find((filter) => filter.key === source.source)?.label ?? source.label;
}

function SourceBlock({ source }: { source: PlaceSource }) {
  if (source.source === "michelin") {
    return (
      <div className="source-block">
        <div className="source-heading">
          <strong>{awardText(source.award)}</strong>
          {source.price && <span> · {source.price}</span>}
          {source.cuisine && <span> · {source.cuisine}</span>}
        </div>
        <div className="source-info">
          <span className="detail-meta">원래 이름: {source.originalName}</span>
          <a href={source.url} target="_blank" rel="noopener noreferrer">미쉐린 가이드 ↗</a>
        </div>
      </div>
    );
  }

  if (source.source === "seoul_heritage") {
    return (
      <div className="source-block">
        <div className="source-heading">
          <strong>서울미래유산</strong>
          <span> · {source.group}</span>
          {source.openedYear && <span> · {source.openedYear}년 개업</span>}
          {source.selectedYear && <span> · {source.selectedYear}년 선정</span>}
        </div>
        <div className="source-info">
          <span className="detail-meta">원래 이름: {source.originalName}</span>
          <a href={source.url} target="_blank" rel="noopener noreferrer">서울미래유산 ↗</a>
        </div>
      </div>
    );
  }

  if (source.source === "good_price") {
    return (
      <div className="source-block">
        <div className="source-heading"><strong>착한가격업소</strong> · {source.category}</div>
        {source.menuName && (
          <div className="detail-meta">
            착한가격 메뉴: {source.menuName}
            {source.menuPrice !== null && ` · ${source.menuPrice.toLocaleString("ko-KR")}원`}
          </div>
        )}
        <div className="source-info">
          <span className="detail-meta">원래 이름: {source.originalName}</span>
          {source.url && <a href={source.url} target="_blank" rel="noopener noreferrer">공공데이터 ↗</a>}
        </div>
      </div>
    );
  }

  return (
    <div className="source-block">
      <div className="source-heading">
        <strong>{sourceLabel(source)}</strong>
        {source.category && <span> · {source.category}</span>}
        {source.year && <span> · {source.year}년</span>}
      </div>
      <div className="source-info">
        <span className="detail-meta">원래 이름: {source.originalName}</span>
        {source.url && <a href={source.url} target="_blank" rel="noopener noreferrer">출처 보기 ↗</a>}
      </div>
    </div>
  );
}

export default function PlaceDetail({
  place,
  onClose,
  presentation = "bubble",
}: {
  place: Place;
  onClose: () => void;
  presentation?: "bubble" | "inline";
}) {
  const googleMapUrl = place.googlePlaceId
    ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${place.name} ${place.address}`)}&query_place_id=${encodeURIComponent(place.googlePlaceId)}`
    : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${place.name} ${place.address}`)}`;

  return (
    <div className={`detail ${presentation === "inline" ? "detail-inline" : ""}`} role="dialog" aria-label={`${place.name} 상세`}>
      <button className="close" onClick={onClose} aria-label="닫기">
        ×
      </button>
      <div className="detail-scroll">
        <h2>{place.name}</h2>
        <div className="detail-meta">{place.category}</div>
        <div className="detail-meta">{place.address}</div>

        <div className="rating-panel" aria-label="플랫폼 평점">
          <RatingLine prefix="K Star" result={place.ratings?.kakao ?? null} />
          <RatingLine prefix="G Star" result={place.ratings?.google ?? null} showCollectedDate />
        </div>

        <div className="badges">
          {place.sources.map((source, index) => (
            <span key={`${source.source}-${index}`} className={`badge ${source.source}`}>
              {source.source === "michelin" ? awardText(source.award) : sourceLabel(source)}
            </span>
          ))}
          {place.matdoriaPick?.selected && <span className="badge matdoria-pick">Matdoria&apos;s Pick</span>}
        </div>

        <div className="detail-sources">
          {place.sources.map((source, index) => (
            <SourceBlock key={`${source.source}-${index}`} source={source} />
          ))}
        </div>

        <div className="actions">
          <a className="btn primary" href={place.kakaoUrl} target="_blank" rel="noopener noreferrer">
            카카오맵에서 보기
          </a>
          <a className="btn google" href={googleMapUrl} target="_blank" rel="noopener noreferrer">
            구글지도에서 보기
          </a>
        </div>
      </div>
    </div>
  );
}
