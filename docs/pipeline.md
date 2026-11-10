# 파이프라인

현재 단계는 **1단계 (소스 수집)** 까지 완료. 2단계 이후는 계획 단계입니다.

## 전체 흐름

```
[1] 수집 (scripts/fetch_*.py)           → data/raw/<날짜>/ , data/processed/*.csv
[2] 매칭 (카카오 로컬 API)               → data/processed/places_matched.csv   (미실행)
[3] 신호 계산 (노트북)                    → 지표 컬럼 추가                        (미실행)
[4] 점수화와 선택 (설정 YAML)             → Top 100                                (미실행)
[5] export (Next.js용 JSON)              → web/public/data/places.json           (미실행)
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

## 2단계: 카카오 매칭 (다음 작업)

1. 입력: 서울미래유산 식음 항목 + 미쉐린 서울 항목
2. 카카오 키워드 검색 (`query` = 이름 + 구 이름), 좌표 기준 반경 검색 병행
3. 후보 점수: 이름 유사도 (정규화 후), 주소 일치, 좌표 거리
4. 자동 채택 기준 (예): 이름 유사도 높음 + 거리 200m 이내. 그 외는 검수 목록
5. 매칭 실패는 drop (D-002)
6. 미쉐린은 영문 이름이라 별도 별칭 표 (`data/aliases/michelin.csv`)가 필요할 수 있음

산출물: `data/processed/places_matched.csv` (`place_id`, 출처별 원본 ID, 카카오 ID, 장소 URL 등)

## 3~5단계 (계획)

- 노트북에서 지표를 계산하고 가중치를 실험합니다. 설정은 YAML로 관리합니다 (D-009).
- Top 100은 점수 순으로 선택합니다. 구별 상한은 없습니다 (D-003).
- export는 Next.js `public/data/`에 JSON으로 저장하고, 빌드 시 포함합니다 (D-010).

## 갱신 절차 (수동, 연 1회 또는 필요 시)

1. 수집 스크립트 재실행
2. 매칭 재실행, 검수 목록 확인
3. 노트북에서 점수 재계산
4. export 후 배포
5. `docs/data-sources.md`의 날짜와 상태 갱신

## 배포 (Vercel)
- 저장소 루트는 Next.js 앱이 아니다. Vercel 프로젝트 설정에서 **Root Directory를 `web`** 으로 지정해야 한다. 루트로 두면 빌드가 실패한다.
- 웹앱은 `web/public/data/places.json`만 읽는다. 배포 시 `data/`나 Python 스크립트는 필요 없다.
- 환경변수: Vercel 프로젝트에 `NEXT_PUBLIC_KAKAO_MAP_KEY`를 등록한다. `.env.local`은 git에 올라가지 않으므로 Vercel에 직접 넣어야 한다.
- 카카오 개발자 콘솔의 JavaScript 키 "플랫폼 > Web 도메인"에 Vercel 배포 도메인(`https://<프로젝트>.vercel.app` 등)을 추가해야 지도가 뜬다 (D-022).
- 루트 `.gitignore`가 `data/raw/`, `.env*`, `.next/`, `node_modules/`를 제외한다. 저장소 전체를 push하는 것은 문제없지만, 원본 데이터는 올라가지 않는다.
- 데이터를 갱신했다면 `scripts/export_places.py`를 실행해 `places.json`을 커밋한 뒤 push하면 재배포된다.
