import type { PlaceSource } from "./types";

export const CURATION_FILTERS = [
  {
    key: "matdoria_pick",
    label: "Matdoria's Pick",
    description: "K/G Review 기준을 모두 충족한 인기 장소",
  },
] as const;

export const SOURCE_FILTERS = [
  { key: "all", label: "전체" },
  { key: "michelin", label: "미쉐린" },
  { key: "seoul_heritage", label: "서울미래유산" },
  { key: "good_price", label: "착한가격업소" },
  { key: "model_restaurant", label: "모범음식점" },
  { key: "seoul_gourmet_100", label: "서울미식 100선" },
  { key: "hundred_store", label: "백년가게" },
  { key: "restaurant_license", label: "영업 인허가" },
] as const;

export type SourceFilter = (typeof SOURCE_FILTERS)[number]["key"];
export type CurationFilter = (typeof CURATION_FILTERS)[number]["key"];
export type ListFilter = SourceFilter | CurationFilter;

export const SOURCE_STATUS: Record<ListFilter, string> = {
  all: "",
  michelin: "미쉐린 데이터가 포함된 장소를 표시합니다.",
  seoul_heritage: "서울미래유산 데이터가 포함된 장소를 표시합니다.",
  good_price: "서울 외식업 1,503건을 정규화했습니다. 카카오 장소와 주소 검증된 항목만 표시합니다.",
  model_restaurant: "공식 CSV 확보 후 정규화·카카오 주소 검증을 거쳐 표시합니다.",
  seoul_gourmet_100: "공식 목록과 재사용 조건을 확인한 뒤 표시합니다.",
  hundred_store: "전국 백년가게 지정 목록 1,511건을 확보했습니다. Kakao 장소 매칭·검수 후 표시합니다.",
  restaurant_license: "서울시 인허가 원본과 업소명·주소가 정확히 일치하는 681곳의 행정상 영업 상태를 표시합니다. 상태는 수일 지연될 수 있습니다.",
  matdoria_pick: "K Review 50+ 및 G Review 250+ 기준을 모두 충족한 장소입니다. 데이터가 없는 것은 낮은 평가를 뜻하지 않습니다.",
};

export function matchesFilter(
  sources: PlaceSource[],
  filter: ListFilter,
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
