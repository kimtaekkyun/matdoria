import type { PlaceSource } from "./types";

export const SOURCE_FILTERS = [
  { key: "all", label: "전체" },
  { key: "michelin", label: "미쉐린" },
  { key: "seoul_heritage", label: "서울미래유산" },
] as const;

export type SourceFilter = (typeof SOURCE_FILTERS)[number]["key"];

export function matchesFilter(sources: PlaceSource[], filter: SourceFilter): boolean {
  return filter === "all" || sources.some((s) => s.source === filter);
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
