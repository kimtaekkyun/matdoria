import type { Place, PlaceSource, MichelinSource, HeritageSource } from "../lib/types";
import { awardText } from "../lib/sources";

function SourceBlock({ source }: { source: PlaceSource }) {
  if (source.source === "michelin") {
    const s: MichelinSource = source;
    return (
      <div className="source-block">
        <div>
          <strong>{awardText(s.award)}</strong>
          {s.price && <span> · {s.price}</span>}
          {s.cuisine && <span> · {s.cuisine}</span>}
        </div>
        <div className="detail-meta">원래 이름: {s.originalName}</div>
        <a href={s.url} target="_blank" rel="noopener noreferrer">
          미쉐린 가이드에서 보기
        </a>
      </div>
    );
  }
  const h: HeritageSource = source;
  return (
    <div className="source-block">
      <div>
        <strong>서울미래유산</strong>
        {h.openedYear && <span> · {h.openedYear}년 개업</span>}
        {h.selectedYear && <span> · {h.selectedYear}년 선정</span>}
      </div>
      <div className="detail-meta">원래 이름: {h.originalName}</div>
      <a href={h.url} target="_blank" rel="noopener noreferrer">
        서울미래유산에서 보기
      </a>
    </div>
  );
}

export default function PlaceDetail({ place, onClose }: { place: Place; onClose: () => void }) {
  return (
    <div className="detail" role="dialog" aria-label={`${place.name} 상세`}>
      <button className="close" onClick={onClose} aria-label="닫기">
        ×
      </button>
      <h2>{place.name}</h2>
      <div className="detail-meta">{place.category}</div>
      <div className="detail-meta">{place.address}</div>

      <div className="badges">
        {place.sources.map((s, i) => (
          <span key={i} className={`badge ${s.source === "michelin" ? "michelin" : "heritage"}`}>
            {s.source === "michelin" ? awardText(s.award) : "서울미래유산"}
          </span>
        ))}
      </div>

      {place.sources.map((s, i) => (
        <SourceBlock key={i} source={s} />
      ))}

      <div className="actions">
        <a className="btn primary" href={place.kakaoUrl} target="_blank" rel="noopener noreferrer">
          카카오맵에서 보기
        </a>
      </div>
    </div>
  );
}
