# 파이프라인

기존 미쉐린·서울미래유산 데이터의 수집, 카카오 매칭, JSON export는 완료했습니다. 새 출처의 실제 수집·매칭과 Matdoria's Pick 조건은 진행 중입니다.

## 전체 흐름

```
[1] 수집 (scripts/fetch_*.py)           → data/raw/<날짜>/ , data/processed/*.csv
[2] 매칭 (카카오 로컬 API)               → data/processed/places_matched.csv   (기존 2개 출처 완료, 신규 출처 대기)
[3] 평점 snapshot 수집 (Google/Kakao)     → data/raw/google/ratings.csv + data/processed/kakao_ratings.csv (완료)
[4] Matdoria's Pick 점수/조건             → data/curation/matdoria_pick.json (초안 설정, 아직 미선정)
[5] export (Next.js용 JSON)               → web/public/data/places.json (평점 포함, 런타임 API 불필요)
```

## 1단계: 수집 (완료)

| 스크립트 | 출력 | 행 수 |
|---|---|---|
| `scripts/fetch_seoul_heritage.py` | `data/processed/seoul_heritage_food.csv` | 103 (음식점 54, 골목 8, 후보 41) |
| `scripts/fetch_michelin.py` | `data/processed/michelin_seoul.csv` | 180 |

실행 방법:

```bash
python scripts/fetch_seoul_heritage.py
python scripts/fetch_michelin.py
```

원본은 `data/raw/<YYYY-MM-DD>/`에 날짜별로 저장되며 git에서 제외합니다.

### 서울미래유산 CSV 열

`ht_no`, `name`, `group`, `address`, `gu_code`, `lat`, `lng`, `opened_year`, `opened_year_snippet`, `built_year_text`, `heritage_selected_year`, `cert_no`, `search_type`, `search_type_dtl`, `description`, `detail_url`, `fetched_at`

- `opened_year_snippet`: 파싱 근거 문장. 검수할 때 사용합니다.
- `built_year_text`: 준공 연도 (개업연도 아님).

## 2단계: 카카오 매칭

- 완료: 미쉐린·서울미래유산 레코드 262건을 카카오 장소 ID에 매칭. 최종 웹 데이터는 high-confidence 매칭만 사용.
- 다음 작업: 착한가격업소·모범음식점 등 새 원본을 출처별로 정규화한 뒤 카카오와 이름·주소를 함께 검증해 매칭. 상호명만으로 자동 채택하지 않는다.

산출물: `data/processed/places_matched.csv` (`place_id`, 출처별 원본 ID, Kakao ID, 장소 URL, 매칭 근거 등)

## 3~5단계 (평점 snapshot, export 및 Matdoria's Pick)

- Kakao 평점은 `python scripts/fetch_kakao_ratings.py`로 현재 `places.json`의 모든 Kakao ID에 요청하고 `data/processed/kakao_ratings.csv`에 집계 필드만 저장합니다. 개별 리뷰는 저장하지 않습니다. `--refresh`는 전부 다시 요청합니다.
- Google snapshot은 `data/raw/google/ratings.csv`의 Place ID/평점 수집 결과를 사용합니다. 신규 source를 검색할 때는 루트 `.env.local`의 `GOOGLE_PLACES_API_KEY`가 필요합니다. 이미 수집한 row를 강제로 갱신하려면 `python scripts/fetch_google_ratings.py --refresh`를 사용합니다 (253건 API 요청/과금 가능).
- `scripts/export_places.py`는 K/G 별점·리뷰 수 snapshot을 `places.json`에 포함합니다. 웹앱은 export JSON만 읽고 rating API를 호출하지 않습니다. snapshot을 갱신할 때 Google/Kakao batch 수집 → `python scripts/export_places.py` → 배포 순서로 진행합니다.
- Matdoria's Pick 규칙은 `data/curation/matdoria_pick.json`에서 관리합니다. 현재 점수 가중치/최소 점수 미설정이라 선정 결과는 0곳입니다. ratings는 Pick score에 포함하지 않습니다.
- 여러 큐레이션 리스트를 지원하며, Top 100 제한과 가중치는 데이터 확인 후 확정합니다.

## 갱신 절차 (수동, 연 1회 또는 필요 시)

1. 수집 스크립트 재실행
2. 매칭 재실행, 검수 목록 확인
3. 노트북에서 점수 재계산
4. export 후 배포
5. `docs/data-sources.md`의 날짜와 상태 갱신

## 배포 (Vercel)
- 저장소 루트는 Next.js 앱이 아니다. Vercel 프로젝트 설정에서 **Root Directory를 `web`** 으로 지정해야 한다. 루트로 두면 빌드가 실패한다.
- 웹앱은 `web/public/data/places.json`만 읽는다. 배포 시 `data/`나 Python 스크립트는 필요 없다.
- 환경변수: Vercel 프로젝트에 `NEXT_PUBLIC_KAKAO_MAP_KEY`만 필요하다. Google Places API 키는 로컬 batch snapshot을 다시 수집할 때만 루트 `.env.local`에 필요하고 웹앱/Vercel 런타임에는 전달하지 않는다.
- 카카오 개발자 콘솔의 JavaScript 키 "플랫폼 > Web 도메인"에 Vercel 배포 도메인(`https://<프로젝트>.vercel.app` 등)을 추가해야 지도가 뜬다 (D-022).
- 루트 `.gitignore`가 `data/raw/`, `.env*`, `.next/`, `node_modules/`를 제외한다. 저장소 전체를 push하는 것은 문제없지만, 원본 데이터는 올라가지 않는다.
- 데이터를 갱신했다면 `scripts/export_places.py`를 실행해 `places.json`을 커밋한 뒤 push하면 재배포된다.
