import type { PlaceSource } from "./types";

export const SOURCE_FILTERS = [
  { key: "all", label: "전체" },
  { key: "michelin", label: "미쉐린" },
  { key: "seoul_heritage", label: "서울미래유산" },
  { key: "good_price", label: "착한가격업소" },
  { key: "model_restaurant", label: "모범음식점" },
  { key: "seoul_gourmet_100", label: "서울미식 100선" },
  { key: "hundred_store", label: "백년가게" },
  { key: "matdoria_pick", label: "Matdoria's Pick" },
] as const;

export type SourceFilter = (typeof SOURCE_FILTERS)[number]["key"];

export const SOURCE_STATUS: Record<SourceFilter, string> = {
  all: "",
  michelin: "미쉐린 데이터가 포함된 장소를 표시합니다.",
  seoul_heritage: "서울미래유산 데이터가 포함된 장소를 표시합니다.",
  good_price: "원본 CSV는 확보했습니다. 카카오 장소 매칭 후 표시됩니다.",
  model_restaurant: "공식 데이터 파일의 실제 다운로드와 장소 매칭을 확인 중입니다.",
  seoul_gourmet_100: "공식 목록과 재사용 조건을 확인한 뒤 표시합니다.",
  hundred_store: "공식 목록과 데이터 제공 경로를 확인한 뒤 표시합니다.",
  matdoria_pick: "출처별 데이터를 바탕으로 Matdoria의 큐레이션 기준을 적용할 예정입니다.",
};

export function matchesFilter(
  sources: PlaceSource[],
  filter: SourceFilter,
  isMatdoriaPick = false,
): boolean {
  if (filter === "all") return true;
  if (filter === "matdoria_pick") return isMatdoriaPick;
  return sources.some((source) => source.source === filter);
}

export function awardText(award: string): string {
  switch (award) {
    case "3 Stars":
      return "미쉐린 3스타";
    case "2 Stars":
      return "미쉐린 2스타";
    case "1 Star":
      return "미쉐린 1스타";
    case "Bib Gourmand":
      return "빕 구르망";
    case "Selected Restaurants":
      return "미쉐린 셀렉티드";
    default:
      return award;
  }
}
