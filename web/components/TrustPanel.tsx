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

  return (
    <details className="trust-panel">
      <summary>
        <span className="trust-panel-mark" aria-hidden="true">i</span>
        <span>Pick 선정 기준</span>
        <span className="trust-panel-chevron" aria-hidden="true">⌄</span>
      </summary>
      <div className="trust-panel-content">
        <div className="trust-panel-lead">
          <strong>두 플랫폼의 Review 수 기준입니다.</strong>
          <p>K Review count {buildInfo.reviewCountThresholds.kakaoReviewCount}개 이상 AND G Review count {buildInfo.reviewCountThresholds.googleUserRatingCount}개 이상을 모두 충족해야 합니다.</p>
        </div>
        <p>count가 미제공·미수집이면 이 기준을 확인할 수 없어 Pick에 포함되지 않습니다. 낮은 품질이나 낮은 별점을 뜻하지 않으며, 0으로 계산하지 않습니다.</p>
        <p className="trust-panel-freshness">
          Matdoria&apos;s Pick 마지막 업데이트: {builtAt ?? "확인할 수 없음"}
        </p>
      </div>
    </details>
  );
}
