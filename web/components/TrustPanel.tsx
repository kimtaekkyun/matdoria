import buildInfo from "../public/data/build-info.json";

function formatBuildDate(value: string | undefined): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Seoul",
  }).format(date);
}

export default function TrustPanel() {
  const builtAt = formatBuildDate(buildInfo.buildTimestamp);
  const reviews = buildInfo.reviewCountThresholds;
  const ratings = buildInfo.ratingThresholds;

  return (
    <section className="pick-about" aria-label="Matdoria와 Pick 선정 기준">
      <p className="pick-about-intro">
        Matdoria는 서울의 식당 정보를 공식·리뷰 데이터로 모아 한곳에서 살펴보는 지도예요.
      </p>
      <p className="pick-about-criteria">
        <span>K Review ≥ {reviews.kakaoReviewCount}</span>
        <span>K Star ≥ {ratings.kakaoRating.toFixed(1)}</span>
        <span>G Review ≥ {reviews.googleUserRatingCount}</span>
        <span>G Star ≥ {ratings.googleRating.toFixed(1)}</span>
      </p>
      <p className="pick-about-note">
        필요한 정보가 없으면 Pick에 포함되지 않으며, 낮은 별점으로 간주하지 않습니다.
        {builtAt ? <span> · {builtAt} 업데이트</span> : null}
      </p>
    </section>
  );
}
