import { meetsPickReviewThresholds } from "../lib/types";
import type { Place, PlaceSource, RatingSnapshot } from "../lib/types";
import { SOURCE_FILTERS, awardText } from "../lib/sources";

type RatingLineProps = { prefix: "K Star" | "G Star"; result: RatingSnapshot | null };

function RatingLine({ prefix, result }: RatingLineProps) {
  const rating = result?.rating ?? null;

  return (
    <div className="detail-rating">
      <span className="detail-rating-label">{prefix}</span>
      <span className="detail-rating-value">
        {rating === null ? (
          <span aria-label="평점 정보 없음">—</span>
        ) : (
          <strong><span className="detail-rating-star" aria-hidden="true">★</span> {rating.toFixed(1)}</strong>
        )}
        {result?.count != null && (
          <span className="detail-rating-count"> ({result.count.toLocaleString("ko-KR")})</span>
        )}
      </span>
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
    const menus = source.menuItems?.length
      ? source.menuItems
      : source.menuName
        ? [{ name: source.menuName, price: source.menuPrice ?? null }]
        : [];
    return (
      <div className="source-block">
        <div className="source-heading"><strong>착한가격업소</strong> · {[source.categoryGroup, source.category].filter(Boolean).join(" · ")}</div>
        {menus.map((menu, index) => (
          <div className="detail-meta" key={`${menu.name}-${index}`}>
            착한가격 메뉴: {menu.name}
            {menu.price !== null && ` · ${menu.price.toLocaleString("ko-KR")}원`}
          </div>
        ))}
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
        {source.foodType && <span> · 대표 음식: {source.foodType}</span>}
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
  const isPickEligible = meetsPickReviewThresholds(place);
  const googleMapUrl = place.googlePlaceId
    ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${place.name} ${place.address}`)}&query_place_id=${encodeURIComponent(place.googlePlaceId)}`
    : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${place.name} ${place.address}`)}`;

  return (
    <div className={`detail ${presentation === "inline" ? "detail-inline" : ""}`} role="dialog" aria-label={`${place.name} 상세`}>
      <button className="close" onClick={onClose} aria-label="닫기">
        ×
      </button>
      <div className="detail-scroll">
        <div className="detail-header">
          <div className="detail-identity">
            <h2>{place.name}</h2>
            <div className="detail-meta">{place.category}</div>
            <div className="detail-meta">{place.address}</div>
          </div>
          <div className="detail-ratings" role="group" aria-label="플랫폼 평점">
            <RatingLine prefix="K Star" result={place.ratings?.kakao ?? null} />
            <RatingLine prefix="G Star" result={place.ratings?.google ?? null} />
          </div>
        </div>

        <div className="badges">
          {place.sources.map((source, index) => (
            <span key={`${source.source}-${index}`} className={`badge ${source.source}`}>
              {source.source === "michelin" ? awardText(source.award) : sourceLabel(source)}
            </span>
          ))}
          {isPickEligible && <span className="badge matdoria-pick">Matdoria&apos;s Pick</span>}
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
