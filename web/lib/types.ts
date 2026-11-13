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

export type GoodPriceSource = {
  source: "good_price";
  label: string;
  category: string;
  menuName: string;
  menuPrice: number | null;
  url: string;
  originalName: string;
};

export type PublicSelectionSource = {
  source: "model_restaurant" | "seoul_gourmet_100" | "hundred_store";
  label: string;
  category?: string;
  year?: number | null;
  url?: string;
  originalName: string;
};

export type PlaceSource = MichelinSource | HeritageSource | GoodPriceSource | PublicSelectionSource;

export type RatingSnapshot = {
  rating: number | null;
  count: number | null;
  collectedAt: string | null;
};

export type PlaceRatings = {
  kakao: RatingSnapshot | null;
  google: RatingSnapshot | null;
};

export type MatdoriaPick = {
  selected: boolean;
  score?: number;
  reasons: string[];
  profileVersion?: string;
};

export type Place = {
  id: string; // 카카오 장소 ID
  name: string;
  address: string;
  category: string;
  lat: number;
  lng: number;
  kakaoUrl: string;
  googlePlaceId?: string;
  ratings?: PlaceRatings;
  sources: PlaceSource[];
  matdoriaPick?: MatdoriaPick;
};
