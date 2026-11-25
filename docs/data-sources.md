# 데이터 소스 카탈로그

최종 업데이트: 2026-11-24

상태 표기: **사용중** (수집 스크립트 있음), **조건부** (약관 또는 신뢰성 확인 필요), **보류**, **제외**.

## 사용중

### 1. 카카오 로컬 API (매칭과 기준 키)

- 용도: 장소 ID, 좌표, 카테고리, `place_url` 확보. 서울미래유산·미쉐린·착한가격업소 항목을 이 ID에 연결
- 공식 문서: https://developers.kakao.com/docs/latest/ko/local/dev-guide
- 확인된 필드: `id`, `place_name`, `category_name`, `phone`, `address_name`, `road_address_name`, `x`, `y`, `place_url`
- 제약: 키워드 검색은 한 번에 최대 45건 (페이지 3 × 15건 수준, 문서 기준). 격자나 반경 검색으로 보완 필요. 일일 쿼터 있음
- 별점과 리뷰 수는 없음 (D-004)
- 상태: 미쉐린·서울미래유산 및 착한가격업소의 장소 매칭에 사용 중. API 응답은 로컬 캐시하고 high 매칭 결과를 export함
- 약관: 검색 결과의 장기 저장과 재배포 가능 기간은 여전히 확인 필요. 웹 공개 전 정책 적합성 검토 필요

### 2. 서울미래유산 (서울기록원)

- 용도: 식음 항목 (음식점, 골목) 및 개업연도
- 소스: 메인 지도 AJAX `POST /main/ajaxMainHeritageList.do` (파라미터: `lat`, `lng`, `distance=15`, `gu`)
- 수집 결과: 전체 499건, 식음 관련 103건 (음식점 54, 음식골목 8, 후보 41)
- 상세 페이지: `/futureHeritageMeet/futureHeritage/view.do?htNo=...`
- 개업연도: 설명 텍스트 파싱, 일부 누락. 확인 필요
- 선정 연도: `certNo` 앞 4자리 (예: `2013-006`)
- 공식 목록과 2021년 "노포식당 50선" 표 (2차 인용) 대조가 필요
- 약관: 서울시 공공 콘텐츠. 저작권 정책 확인 필요
- 스크립트: `scripts/fetch_seoul_heritage.py`

### 3. 미쉐린 가이드 (커뮤니티 데이터셋)

- 소스: https://github.com/ngshiheng/michelin-my-maps (MIT), 파일 `data/michelin_my_maps.csv`
- 이 저장소의 성격: 저장소 소유자가 만든 **Go 크롤러**(Colly, `cmd/mym`)가 공식 가이드 페이지(guide.michelin.com)를 긁어 CSV를 생성한다. 저장소 자체는 공식 API가 아니다.
- 취득 방식: `scripts/fetch_michelin.py`가 `main` 브랜치의 raw 파일을 내려받는다 (크롤러는 실행하지 않음). 우리 쪽에서 긁은 것이 아니다.
- 현재 사용 버전 (2026-11-10 기준 확인):
  - 업스트림 커밋: `15ef8a52417c992f0688b8bc19c433fe925c4b98` ("chore(data): update generated csv", 2026-11-03, 저자 Jerry Ng, GPG 서명)
  - 우리가 내려받은 날짜: 2026-11-09 (`data/raw/michelin/2026-11-09/`)
  - 데이터 기준일: 2026-11-03 커밋. 크롤링 시점은 이보다 앞일 수 있으며 확인할 수 없다.
- 이전 커밋 이력 (업데이트 주기 참고): 2026-07-08, 08-03, 09-04, 10-03, 11-03 (대략 월 1회)
- 용도: 서울 미쉐린 항목 (등급, 좌표, 영문 주소, 공식 가이드 URL)
- 수집 결과: 서울 180곳
- 제약: 영문 이름과 주소라 카카오 매칭이 어렵다. 공식 가이드 페이지와 교차 확인 필요
- 공식 개발자 포털 (developer.michelin.com/en): 공개 API 카탈로그에서 레스토랑 가이드 API는 확인되지 않음. 로그인 후 추가 API가 보일 수 있어 확인 필요
- 스크립트: `scripts/fetch_michelin.py`

## 조건부

### 4. 착한가격업소 (행정안전부 등록현황)

- 소스: 공공데이터포털 [15172358](https://www.data.go.kr/data/15172358/fileData.do)
- 조사일: 2026-11-12. CSV 실제 다운로드 및 파싱 완료. 2026-09-30 스냅샷, 12,935행·17컬럼, 서울 2,155행 확인. 서울 내 `외식업` 1,503행, `기타개인서비스업` 652행
- 실제 컬럼에 업소명, 주소, 업종 대/세분류, 메뉴 수, 최대 4개 착한가격 메뉴명·가격이 포함됨
- 원본: `data/raw/good_price/2026-11-12/good_price_20260930.csv` (`/data/raw/` git 제외)
- 정규화: `python scripts/prepare_public_sources.py` → `data/processed/good_price_seoul.csv` (서울 `구분=외식업`만 보존하고 최대 4개 메뉴를 배열로 저장)
- 용도: 맛 평점이 아니라 가성비 프로필의 선정 신호 또는 필터
- 서울 외식업 1,503건을 Kakao로 조회해 주소 검증된 단일 후보 1,002건을 high 매칭함. 나머지 501건은 미매칭 또는 후보 모호로 `data/processed/match_public_review.csv`에 분리함. 상세 메뉴는 최대 4개를 Matdoria에 표시함
- 이름만으로는 오매칭이 발생하므로 Kakao 음식점 카테고리, 상호, 주소(구·도로명/번지)가 모두 확인된 단일 후보만 자동 매칭함

### 5. 모범음식점 (행정안전부 전국 통합)

- 소스: 공공데이터포털 [15076765](https://www.data.go.kr/data/15076765/fileData.do)
- 조사일: 2026-11-12. 페이지의 2025-11-27 수정 메타데이터와 CSV 제공을 확인. 업소명, 주소, 음식 유형·주된 음식 등 기본정보를 제공하며 이용허락범위 제한 없음으로 표시
- 갱신 안내: 자동 갱신, 2일 전 기준 현행화라고 포털에 표시됨
- 제공 파일 URL(`https://file.localdata.go.kr/file/excellent_restaurant_info/info`)은 조사 환경에서 HTTP 403. 원본 파일과 실제 컬럼은 아직 확보하지 못함
- 원본 확보 후 `python scripts/prepare_public_sources.py --model-csv <원본 CSV>`로 정규화하도록 준비함. 업소명·주소를 필수로 확인하고 음식 유형·주된 음식·연도는 있는 경우 보존함
- 용도: 맛 점수가 아닌 공공 지정/위생 성격의 보조 신호
- 서울 자치구별 CSV, 허가번호 등 실제 컬럼, 전국 파일 서울 필터는 원본 확보 후 검증 필요

### 6. 서울 일반음식점 인허가 (서울 열린데이터광장 OA-16094)

- 공식 카탈로그: 공공데이터포털 [15071760](https://www.data.go.kr/data/15071760/fileData.do)에서 서울 열린데이터광장 [OA-16094](https://data.seoul.go.kr/dataList/OA-16094/S/1/datasetView.do)로 연결
- 라이선스: 공공저작물 제1유형(출처표시); 서울 페이지는 이용허락범위 제한 없음. 최신 값은 약 2~3일 지연됨
- 2026-11-22 snapshot: 540,008행, 영업/정상 120,077 · 폐업 419,931. 원본 46열·CP949는 `data/raw/seoul_restaurant_licenses/`에 git 제외로 보관하고, 분석 필드는 24열 gzip `data/processed/seoul_restaurant_licenses.csv.gz`로 보존
- 상호와 정규화 도로명주소가 정확히 일치한 681개 canonical 장소에만 상태 정보를 연결: 663 영업/정상, 18 폐업. 상호나 주소만으로 찾은 16,722 후보는 검수 파일에 분리. 인허가일은 현재 인허가 기록의 날짜이지 연속 운영기간의 증명이 아님
- 수집/정규화: `python scripts/fetch_seoul_restaurant_licenses.py`; 오프라인 매칭: `python scripts/match_seoul_restaurant_licenses.py`. 상태는 표시 정보일 뿐 Matdoria's Pick 기준에는 반영하지 않음. 자세한 내용은 [seoul_restaurant_licenses_audit.md](seoul_restaurant_licenses_audit.md)

## 보류

### 7. 소상공인 상가(상권)정보

- 용도: 상호, 주소, 좌표, 업종
- 개업일 필드 유무: 확인 필요
- 상태: 매칭 보조 용도로 검토

### 8. 플랫폼 평점 (카카오·네이버·Google 등)

- 카카오 로컬 API: 별점·리뷰 수 필드 없음. Kakao Map의 undocumented 내부 리뷰 API를 배치 수집해 243개 장소 중 236개 평점 스냅샷 확보, 7곳은 평점 없음. 원본 결과는 `data/processed/kakao_ratings.csv`, export 결과는 공개 `places.json`에 저장. 사용자 결정에 따라 공개 표시 중이나 내부 API의 공식 허가/안정성은 확인되지 않았고 위험은 미해결 (D-032, D-039). 조사 절차는 [kakao-rating-api-walkthrough.html](kakao-rating-api-walkthrough.html).
- Google Places API (New): high 매칭 253개 source row에 Google Place ID가 있고, 251개에 평점 스냅샷이 있음. 238건은 source 좌표 100m 이내, 15건은 `far`. 통합 장소에 모호성 없이 연결된 222개 Google 스냅샷만 공개 `places.json`에 포함하며, 런타임에는 API를 호출하지 않음. `data/raw/google/ratings.csv`는 Git 추적 중이다. 사용자 결정에 따른 공개 사용이며 Google 콘텐츠 저장·공개 정책 적합성은 검증되지 않았고 위험은 미해결. 다음 snapshot 수집 시에만 Google API 키가 필요하며 Vercel 런타임 키는 불필요 (D-032, D-039).
- 네이버·카카오/식신 등 사용자 평점: matdoria에서 사용할 수 있는 허가된 일괄 API·데이터 라이선스를 확인하지 못함. 비공식 페이지 스크래핑은 하지 않음

## 수집했지만 앱에 연결하지 않은 데이터

### 서울 광진구 음식점 위생등급

- 공식 Data.go.kr [15112215](https://www.data.go.kr/data/15112215/fileData.do), 이용허락범위 제한 없음. 2025-12-31 snapshot / 2026-01-20 portal update.
- 원본 1,008,200개 record slot 중 1,008,009개는 전체 빈 row placeholder였고, 유효한 업소 레코드는 191개였습니다. 정규화 파일은 `data/processed/gwangjin_hygiene.csv`; 다운로드 스냅샷은 `data/raw/gwangjin_hygiene/` 아래에 있습니다.
- 등급 표기(매우우수/우수/좋음)는 2026-03-16 단일 `적합` 기준 변경 전 데이터입니다. 현재 장소와 exact name/address로 검증된 매치는 없으며, 한 주소 일치 후보도 업소명이 달라 거부했습니다. 웹앱·Pick에 연결하지 않습니다.
- 전국 MFDS 위생등급 API [15060883](https://www.data.go.kr/data/15060883/openapi.do)는 별도 Data.go.kr service key와 활용신청이 필요해 이번에는 호출하지 않았습니다. 상세는 [seoul_restaurant_licenses_audit.md](seoul_restaurant_licenses_audit.md) 참조.

## 추가 조사 대상 (현재 자동 수집하지 않음)

| 소스 | 조사 상태 |
|---|---|
| 블루리본 서베이 | 공식 도메인이 조사 요청에 HTTP 403을 반환. 공개 일괄 데이터/API와 재사용 권리를 확인하지 못함. 도입 여부 재검토 중 |
| 서울미식 100선 | 공식 2026 목록과 catalogue PDF 확인. 이용 약관 13조는 prior approval 없이 복사·재배포를 금지하고, 공개 reuse license를 찾지 못해 수집 보류 (see [audit](seoul_gourmet_100_audit.md)). |
| 서울 오래가게 | 공식 목록/API의 일괄 수집 경로와 이용 조건 미확인 |

## 제외

| 소스 | 사유 |
|---|---|
| 업무추진비 결제 데이터 | 기존 justhere 방식과 겹침 (D-006) |
| 네이버 지역검색, 블로그 검색 | 네이버 제외 (D-001), 블로그는 주관적 (D-005) |
| 망고플레이트, 캐치테이블 등 리뷰 플랫폼 페이지 스크래핑 | 공식 허가 경로 확인 없이 스크래핑하지 않음 |
| 돼동여지도, 먹을지도 등 가공 지도 | 파생 데이터이며 출처가 비공식. 참고만 함 |

## 신뢰도 주의 (미쉐린)
- 원본은 커뮤니티 크롤러가 만든 GitHub 데이터셋이다. 실시간이 아니며, 데이터 기준일은 업스트림 커밋 2026-11-03이다 (D-026).
- `source_snapshot`(2026-11-09)은 우리가 내려받은 날짜다. 데이터 기준일이 아니다.
- 웹앱에 표시하는 등급과 목록은 공식 가이드와 다를 수 있다. 배포 전 샘플 확인을 권장한다.

## 공공 출처 파이프라인

```bash
python scripts/prepare_public_sources.py
python scripts/match_public_sources.py --limit 20  # Kakao API 매칭 표본 확인
python scripts/match_public_sources.py             # 표본 검수 후 전체 처리
python scripts/export_places.py
```

- Kakao 주소 검증 매칭은 `data/processed/public_sources_matched.csv`, 미매칭·모호 후보는 `data/processed/match_public_review.csv`에 저장한다. Kakao 응답 캐시는 `data/raw/kakao_public_cache/`이며 git 제외 대상이다.
- 착한가격업소 전체 처리는 서울 외식업 1,503건에 대한 Kakao 검색 요청을 발생시킨다. 먼저 `--limit` 표본을 확인하고, 주소가 검증된 단일 후보만 `places.json`에 추가한다.
- 모범음식점은 원본 CSV를 확보하기 전까지 정규화·장소 데이터가 없다. 공식 파일 확보 시 `--model-csv` 옵션으로 같은 처리 흐름에 추가한다.
- 상세 화면에는 착한가격 메뉴와 모범음식점의 업태·주된 음식·연도를 가능한 범위에서 표시한다. 해당 지정은 맛 평점이나 맛 점수와 구분한다.

## Matdoria's Pick 및 빌드 추적 (2026-11-20)

- 현재 데이터셋: 1,229개 Kakao 장소 (미쉐린 168, 서울미래유산 63, 착한가격업소 1,002); 모범음식점 원본은 미확보.
- Pick 프로필 v2 초안 `data/curation/matdoria_pick_score_v1.json`: Kakao Review 50개 이상 AND Google Review 250개 이상을 모두 요구합니다. 현재 오래된 snapshot에서 양쪽 Review 수가 있는 장소는 207곳, 기준 통과는 91곳입니다. 별점 평균·미쉐린 등급·공공 지정은 이 Pick 기준에 쓰지 않습니다. 수집 누락은 낮은 평가가 아니라 기준 확인 불가입니다.
- `data/processed/build_history.jsonl`과 `data/processed/matdoria_pick_scores/`에 profile/input/code hashes, build timestamp, source snapshot·K/G 수집 시각, 커버리지, 장소별 evidence를 내부 보존한다. 공개 `web/public/data/build-info.json`에는 Pick 업데이트 시각과 개수만 둔다.
- Kakao 내부 평점 API의 재사용 조건과 Google Places snapshot 저장·공개 조건은 검증되지 않았다. 사용 중인 snapshot이 남아 있더라도 신규 수집이나 사용 확대의 승인을 뜻하지 않는다. 이번 Pick 변경은 기존 snapshot만 이용했으며 재수집은 하지 않았다. 공개 배포 전 재사용 권한을 확인한다.

### Pick 프로필 업데이트 (2026-11-25)

- 프로필 v2.1은 기존 review count 기준에 별점 최소값을 추가했습니다: Kakao Review ≥50 AND Kakao Star ≥3.5 AND Google Review ≥250 AND Google Star ≥4.0.
- 기존 snapshot만 사용해 재수집 없이 export했습니다. 전체 1,229곳 중 58곳이 현재 조건을 모두 충족합니다. 네 조건 중 어느 하나라도 데이터가 없거나 모호하면 판정에서 제외하되 낮은 평가로 해석하지 않습니다.
- 상세 판단 및 당시 v2 기록은 [decisions.md](decisions.md)의 D-042 및 D-043을 참조합니다.

## 새로 수집한 공개 데이터: 백년가게 지정목록 (2026-11-20)

- 공식 출처: 소상공인시장진흥공단, 공공데이터포털 [15132695](https://www.data.go.kr/data/15132695/fileData.do).
- 페이지 표시: CSV, 1,511행, 수정일 2026-08-30, 이용허락범위 제한 없음, 로그인 없이 다운로드 가능. 파일 스냅샷명 기준일은 2026-08-20.
- 원본: `data/raw/hundred_store/2026-11-20/hundred_stores_20260820.csv` (raw는 git 제외); 정규화: `data/processed/hundred_stores.csv` (1,511행, 원본 필드 보존 + source URL/snapshot/수집 시각).
- 재실행: `python scripts/fetch_hundred_stores.py`; 테스트: `python -m unittest discover -s tests -p 'test_hundred_stores.py' -v`.
- 이 목록은 전국 업소이며 음식점/영업기간 필드가 없습니다. 현재 Kakao 장소 매칭과 Pick 점수에는 아직 넣지 않았고, 추후 분류·매칭 검수 후 별도 지표로 검토합니다. 상세 기록은 [public-data-audit.md](public-data-audit.md) 참조.

## 새로 수집한 공개 데이터: 서울 일반음식점 인허가 정보 (2026-11-23)

- 공식 출처: Data.go.kr [15071760](https://www.data.go.kr/data/15071760/fileData.do) → 서울 열린데이터광장 [OA-16094](https://data.seoul.go.kr/dataList/OA-16094/S/1/datasetView.do). 공공저작물 제1유형(출처표시), CSV export, 일일 갱신, 약 2~3일 지연.
- raw snapshot: `data/raw/seoul_restaurant_licenses/2026-11-23/` (git 제외), source 기준일 2026-11-22. 정규화: `data/processed/seoul_restaurant_licenses.csv.gz` 540,008행 × 24 분석 열. 전체 raw는 46열로 로컬 보존.
- 상태 분포: 폐업 419,931, 영업/정상 120,077. 인허가일은 현재 인허가 기록의 시작이지 같은 업소가 같은 장소에서 연속 운영된 기간을 증명하지 않습니다.
- canonical 목록과 업소명+도로명주소가 정확히 일치한 681곳(702 인허가 기록)을 내부 분석용 `data/processed/seoul_restaurant_licenses_matched.csv`에 연결했습니다: 영업/정상 663, 폐업 18. 16,722 후보는 별도 검수 파일에 보존하고, 522,584 무후보 원본 행은 gzip 원본/정규화 입력에 유지합니다.
- 사용자 의견에 따라 이 행정 상태는 Kakao 지도에 등록되어 있는지를 대체하지 못하므로 web app에서 제거했습니다. Pick 자격·점수에도 쓰지 않고 repository 내부 분석 데이터로만 유지합니다.
- 재수집/정규화: `python scripts/fetch_seoul_restaurant_licenses.py`; 매칭: `python scripts/match_seoul_restaurant_licenses.py`. 상세 분석은 [seoul_restaurant_licenses_audit.md](seoul_restaurant_licenses_audit.md)를 참조합니다.
