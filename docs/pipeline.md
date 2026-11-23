# 파이프라인

미쉐린·서울미래유산·착한가격업소를 정규화·매칭해 JSON export에 반영하고, 서울 일반음식점 인허가 자료를 정확 매칭한 상태 보조 신호로 추가했습니다. 모범음식점 원본은 공식 URL 403으로 미확보입니다.

## 전체 흐름

```
[1] 수집/정규화 (scripts/fetch_*.py)       → data/raw/<날짜>/ + processed CSV/GZip
[2] 매칭/상태 보강                         → places_matched.csv + public_sources_matched.csv + seoul_restaurant_licenses_matched.csv
[3] 평점 snapshot 수집 (Google/Kakao)     → data/raw/google/ratings.csv + data/processed/kakao_ratings.csv (완료)
[4] Matdoria's Pick 점수/근거              → data/curation/matdoria_pick_score_v1.json
[5] export + lineage snapshot              → web/public/data/places.json + build-info.json
                                           → data/processed/matdoria_pick_scores/<timestamp>.json
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

- 미쉐린·서울미래유산 레코드 262건에 Kakao 후보를 연결했습니다. 최종 웹 데이터는 high-confidence 매칭만 사용합니다.
- 이름만으로 high가 됐던 16건 중 Kakao 카테고리가 음식점 또는 확인된 먹자골목이 아닌 건은 현재 medium으로 내려 웹 데이터에서 제외했습니다. 재매칭/수동 장소 검증 후에만 다시 high로 올립니다 (D-040).
- 기존 결과는 `data/processed/places_matched.csv`입니다. Kakao `high` 매칭만 export합니다.
- 착한가격업소 서울 `구분=외식업` 1,503행을 정규화했고, 최대 4개 착한가격 메뉴·가격을 보존합니다.
- Kakao 검색 표본 20건을 검수한 뒤 전체 매칭했습니다. Kakao 음식점 카테고리, 상호 유사도, 주소가 검증된 단일 후보 1,002건을 `public_sources_matched.csv`에 high로 저장했습니다. 나머지 501건은 `match_public_review.csv`에 후보와 함께 보존했습니다. Kakao 검색 응답은 `data/raw/kakao_public_cache/`에 캐시합니다.
- 모범음식점은 공식 원본 URL이 현재 403을 반환해 데이터 0건입니다. 파일을 확보하면 `python scripts/prepare_public_sources.py --model-csv <원본 CSV>`로 동일한 정규화·매칭에 넣습니다.
- `scripts/match_seoul_restaurant_licenses.py`는 수집된 서울 일반음식점 인허가 snapshot을 현재 Kakao canonical 목록과 상호·도로명주소 exact match로만 연결합니다. 540,008개 원본 중 681개 장소에 상태를 붙였으며, 애매한 후보는 별도 review CSV에 둡니다. 네트워크/API 호출은 없습니다.
- `scripts/export_places.py`는 기존·공공 source matches와 인허가 상태 match를 합칩니다. 매칭되지 않았거나 모호한 원본은 자동 연결하지 않습니다.
- 현재 `places.json`은 총 1,229곳이며 착한가격업소 1,002곳, 일반음식점 인허가 상태 연결 681곳(663 영업/정상, 18 폐업)을 포함합니다. 별도 백년가게 원본은 1,511행 확보됐지만 아직 Kakao 매칭 전입니다. 모범음식점은 원본 미확보로 미포함입니다.

산출물: `places_matched.csv`, `public_sources_matched.csv`, `match_public_review.csv` (원본 ID, Kakao 장소 ID, 주소, 매칭 근거 등)

## 3~5단계 (평점 snapshot, export 및 Matdoria's Pick)

- 공공·행정 데이터 상세에는 착한가격 메뉴/가격과 (매칭된 경우) 일반음식점의 행정상 영업 상태를 표시합니다. 인허가 상태는 실시간 영업 확인이나 연속 운영기간 증명이 아니며 Matdoria's Pick 기준에는 반영하지 않습니다.

- Kakao 평점은 `python scripts/fetch_kakao_ratings.py`로 현재 `places.json`의 모든 Kakao ID에 요청하고 `data/processed/kakao_ratings.csv`에 집계 필드만 저장합니다. 개별 리뷰는 저장하지 않습니다. `--refresh`는 전부 다시 요청합니다.
- Google snapshot은 `data/raw/google/ratings.csv`의 Place ID/평점 수집 결과를 사용합니다. 신규 source를 검색할 때는 루트 `.env.local`의 `GOOGLE_PLACES_API_KEY`가 필요합니다. 이미 수집한 row를 강제로 갱신하려면 `python scripts/fetch_google_ratings.py --refresh`를 사용합니다 (253건 API 요청/과금 가능).
- `scripts/export_places.py`는 K/G 별점·리뷰 수 snapshot을 `places.json`에 포함합니다. 웹앱은 export JSON만 읽고 rating API를 호출하지 않습니다. snapshot을 갱신할 때 Google/Kakao batch 수집 → `python scripts/export_places.py` → 배포 순서로 진행합니다.
- Matdoria's Pick v2는 `data/curation/matdoria_pick_score_v1.json`에서 설정한 Kakao Review ≥50 AND Google Review ≥250을 동시에 요구합니다. 이는 두 플랫폼 count를 모두 보유한 장소 207곳 중 91곳을 선택합니다. 미수집·모호한 값은 Pick 자격을 입증하지 못하지만 낮은 품질로 해석하지 않습니다.
- Michelin·서울미래유산·착한가격업소·백년가게·영업 인허가 상태는 독립적인 원본 신호로 보존하며 현재 Pick 선택에는 반영하지 않습니다. 현재 데이터는 1,229개 Kakao 장소이며 모범음식점 원본은 미확보 상태입니다.
- 점수 snapshot과 `data/processed/build_history.jsonl`에는 프로필 버전·입력/코드 SHA-256·커버리지·장소별 근거·출처/평점 수집 시각을 내부 기록합니다. 기존 snapshot은 덮어쓰지 않습니다.
- 공개 `web/public/data/build-info.json`에는 Pick 빌드 시각과 선정 개수만 둡니다. 앱에는 이 업데이트 시각과 선정 기준만 표시하며, K/G 별점·출처 데이터의 수집 시각은 노출하지 않습니다.
- Kakao/Google 별점 snapshot은 기존 JSON에 표시 중이지만, 이는 저장·재사용 허가를 검증했다는 뜻이 아닙니다. Kakao 내부 API의 허가/안정성 및 Google 콘텐츠 저장·공개 조건은 미해결 위험입니다. 정책 검토 전에는 Kakao 비공개 API와 Google 평점 snapshot을 재수집하지 않습니다.
- 점수 기준은 draft이며 Top 100 강제 제한은 두지 않습니다. Kakao/Google Review count snapshot의 저장·파생 사용 조건과 미쉐린 커뮤니티 데이터셋의 원자료 재배포 조건을 공개 배포 전에 확인해야 합니다.

## 갱신 절차

### 현재 확보된 입력으로 로컬 재빌드

```bash
python scripts/export_places.py
cd web && npm run lint && npm run build
```

`export_places.py`는 네트워크/API를 호출하지 않습니다. 매칭 CSV와 점수 프로필에서 Pick, 점수 audit snapshot, `places.json`, `build-info.json`, 변경 이력을 재생성합니다. 기존 점수 snapshot은 덮어쓰지 않습니다. 재현이 필요하면 `--build-timestamp 2026-11-20T00:00:00Z`처럼 고정 시간을 지정하되, 해당 snapshot 경로가 이미 있으면 덮어쓰기를 거부합니다.

### 원본 갱신 후 재빌드

1. 권한 및 이용 조건이 확인된 공식 공개 파일/API만 수집합니다.
2. 정규화 스크립트를 실행하고 원본 기준일·수집 시각을 보존합니다. 새 데이터 수집은 예: `python scripts/fetch_hundred_stores.py`, `python scripts/fetch_seoul_restaurant_licenses.py`.
3. Kakao Local API 매칭을 갱신할 때는 쿼터/호출량과 매칭 검수 결과를 확인하고 high-confidence 단일 후보만 반영합니다.
4. 서울 인허가 snapshot을 갱신했다면 `python scripts/match_seoul_restaurant_licenses.py`로 exact 주소 매칭을 재생성합니다.
5. `python scripts/export_places.py`를 실행한 뒤 `build-info.json`, audit snapshot, 입력 해시와 변화 이력을 확인합니다.
6. 정적 산출물을 검토하고 배포합니다. Review threshold와 다음 프로필은 notebook에서 커버리지·결과 수를 비교해 갱신합니다.

API 키가 필요한 갱신은 비용·쿼터 및 재사용 조건 확인 후 별도로 실행합니다. 사용자 정책이나 접근 제한을 우회하는 수집은 하지 않습니다.

## 배포 (Vercel)
- 저장소 루트는 Next.js 앱이 아니다. Vercel 프로젝트 설정에서 **Root Directory를 `web`** 으로 지정해야 한다. 루트로 두면 빌드가 실패한다.
- 웹앱은 `web/public/data/places.json`과 `web/public/data/build-info.json` 정적 산출물을 읽는다. 배포 시 `data/`나 Python 스크립트는 필요 없다.
- 환경변수: Vercel 프로젝트에 `NEXT_PUBLIC_KAKAO_MAP_KEY`만 필요하다. Google Places API 키는 로컬 batch snapshot을 다시 수집할 때만 루트 `.env.local`에 필요하고 웹앱/Vercel 런타임에는 전달하지 않는다.
- 카카오 개발자 콘솔의 JavaScript 키 "플랫폼 > Web 도메인"에 Vercel 배포 도메인(`https://<프로젝트>.vercel.app` 등)을 추가해야 지도가 뜬다 (D-022).
- 루트 `.gitignore`가 `data/raw/`, `.env*`, `.next/`, `node_modules/`를 제외한다. 저장소 전체를 push하는 것은 문제없지만, 원본 데이터는 올라가지 않는다.
- 데이터를 갱신했다면 `scripts/export_places.py`로 정적 JSON 두 파일을 재생성하고 검토 후 커밋/push하면 재배포된다. Production 배포는 Vercel 설정과 도메인 등록이 완료된 뒤 수행한다.
