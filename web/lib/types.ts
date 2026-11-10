export type MichelinSource = {
  source: "michelin";
  label: string;
  award: string; // "3 Stars" | "2 Stars" | "1 Star" | "Bib Gourmand" | "Selected Restaurants"
  price: string;
  cuisine: string;
  url: string;
  originalName: string;
};

export type HeritageSource = {
  source: "seoul_heritage";
  label: string;
  group: string; // "음식점" | "음식 골목" | 기타
  openedYear: number | null;
  selectedYear: number | null;
  url: string;
  originalName: string;
};

export type PlaceSource = MichelinSource | HeritageSource;

export type Place = {
  id: string; // 카카오 장소 ID
  name: string;
  address: string;
  category: string;
  lat: number;
  lng: number;
  kakaoUrl: string;
  sources: PlaceSource[];
};
