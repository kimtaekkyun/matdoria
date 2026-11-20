# Public data audit: 백년가게 지정 현황

조사일: 2026-11-20 UTC
데이터셋: **15132695**, 소상공인시장진흥공단_전국 백년가게 지정리스트 현황 정보

## 공식 출처와 이용 조건

- 공식 데이터셋 페이지: https://www.data.go.kr/data/15132695/fileData.do
- 제공기관: 소상공인시장진흥공단
- 포털 표시: CSV, 1,511건, 수정일 2026-08-30, 연간 갱신, 무료, 파일은 로그인 없이 다운로드 가능.
- 라이선스/이용조건 증거: 페이지의 Schema.org `license.name` 및 이용조건 표에 **이용허락범위 제한 없음**으로 표시. 정책 링크: https://www.data.go.kr/ugs/selectPortalPolicyView.do
- 페이지에 표시된 파일 데이터명은 `_20260820`으로 끝난다. 이를 파일 스냅샷 날짜 `2026-08-20`으로 기록했고, 포털 수정일 `2026-08-30`은 별도 보존했다.

## 취득 및 산출물

이 데이터셋은 직전 작업에서 공식 페이지의 다운로드 버튼 흐름으로 이미 취득·검증되어 있었으므로, 이번 경로 정리에서는 포털에 다시 요청하지 않았다. 기존에 저장된 원본 CSV를 새로 요청한 경로로 그대로 복사하고 정규화했다. 직전 취득 시 포털의 파일유형 확인은 `result=true`였고, 공식 제한/CAPTCHA 확인은 `needCaptcha=false`; CAPTCHA·403·로그인 요구는 없었다. 포털은 수정일이 90일 이내라는 일반 안내를 표시했다. 우회나 다른 경로 사용은 없었다.

정확한 전송 이력: 직전 작업에서 다운로드 응답을 먼저 메모리로 확인한 뒤 저장용으로 다시 받았으므로, 포털 파일 응답은 총 2회였다(첫 응답은 저장하지 않았고, 마지막 응답만 기존 raw 스냅샷으로 보존). 이번 작업은 `--from-raw`를 이용해 네트워크 다운로드 없이 산출물 경로만 정리했다. 따라서 **이번 작업에서 새 포털 다운로드 요청은 0회**다. 향후 일반 실행은 스크립트가 공식 다운로드 흐름으로 파일 응답 1회를 요청한다.

| 경로 | 내용 |
|---|---|
| `data/raw/hundred_store/2026-11-20/hundred_stores_20260820.csv` | 요청된 단수형 경로의 원본 바이트 스냅샷, 88,530 bytes |
| `data/processed/hundred_stores.csv` | 정규화 CSV, 1,511행 × 9열 |
| `scripts/fetch_hundred_stores.py` | 공식 다운로드 + 정규화 스크립트. CAPTCHA/차단이면 중단하고 재시도/우회하지 않으며, 산출물은 기존 파일을 덮어쓰지 않음. `--from-raw`는 보유 원본의 오프라인 재정규화용 |
| `tests/test_hundred_stores.py` | 원본 ID/필드 보존과 provenance 필드를 확인하는 정규화 fixture 테스트 |

원본 SHA-256: `63f36209fe8dc17e1c23107ae268ada87b9aff5c34c47fdba60d94024f4c9094`.

## 행·열 및 정규화

포털이 보고한 1,511행과 CSV 파싱 결과가 일치한다. 헤더를 제외한 **1,511개 레코드**, `연번` 1,511개 모두 비어 있지 않고 고유하다. 원본 네 열의 모든 값을 정규화 파일에서도 대조해 보존을 확인했다.

- 원본 열(4): `연번`, `업체명`, `업체주소`, `연락처`
- 정규화 열(9): 원본 4열 + `source`, `source_url`, `source_snapshot`, `collected_at`, `source_modified_at`
- CSV 인코딩: CP949
- 출처 메타데이터: `source=hundred_store`; 공식 페이지 URL; `source_snapshot=2026-08-20`; `source_modified_at=2026-08-30`; `collected_at=2026-11-20T12:35:51Z` (기존 저장 raw 파일 시각 기준)

## 재실행

보유 raw를 다시 정규화할 때:

```bash
python scripts/fetch_hundred_stores.py \
  --collection-date 2026-11-20 \
  --collected-at 2026-11-20T12:35:51Z \
  --from-raw data/raw/hundred_store/2026-11-20/hundred_stores_20260820.csv \
  --source-modified-at 2026-08-30 \
  --expected-rows 1511
```

새 공식 스냅샷을 받을 때는 `--from-raw` 없이 실행한다. 기존 기본 normalized 출력이 있으면 스크립트는 다운로드 전에 덮어쓰기 방지로 중단하므로, 새 버전은 `--normalized-output`에 새 경로를 지정해야 한다.

테스트:

```bash
python -m unittest discover -s tests -p 'test_hundred_stores.py' -v
```

## 한계와 후속 사용 주의

- 목록은 전국 백년가게 지정 현황이며 식당 전용이 아니다. 실제 열에는 업종/음식 분류가 없고, 비음식 소매점도 포함된다. 음식점 필터와 개별 Matdoria 장소 매칭은 별도 근거 없이 적용하지 않았다.
- 지정 현황은 공공 지정 신호일 뿐, 이 파일에는 개업연도나 실제 운영기간이 없어 개별 업소가 100년 운영했다는 사실을 독립적으로 증명하지 않는다.
- 연락처 및 재배포 조건은 사용 시 포털의 최신 조건을 다시 확인한다. 이번 산출물은 웹앱·Pick 프로필·점수 산정에 연결하지 않았다.
- `data/raw/`는 저장소 `.gitignore` 대상이므로 raw 파일은 현재 작업 디렉터리에 있지만 일반 Git status에는 표시되지 않는다.
