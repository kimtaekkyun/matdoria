# matdoria 문서

개인 맛집 지도 프로젝트 문서 모음입니다. 요구사항과 결정사항은 여기에 기록하고, 결정이 바뀌면 `decisions.md`에 새 항목을 추가합니다.

| 문서 | 내용 |
|---|---|
| [requirements.md](requirements.md) | 요구사항과 범위 |
| [decisions.md](decisions.md) | 결정 기록 (날짜별, 번호 부여) |
| [data-sources.md](data-sources.md) | 데이터 소스 카탈로그와 상태 |
| [pipeline.md](pipeline.md) | 수집, 매칭, 점수화, export 절차, 배포 |
| [scoring-strategy.md](scoring-strategy.md) | DB 구조, 점수 전략, 외부 데이터 소스 실현 가능성 조사 |
| [score_review.ipynb](../notebooks/score_review.ipynb) | 로컬 score snapshot 커버리지·임계값 민감도·선정 근거 분석 |
| [seoul_gourmet_100_audit.md](seoul_gourmet_100_audit.md) | 서울미식 100선 공식 출처와 재사용 조건 조사 결과 |
| [rating-api-experiment.md](rating-api-experiment.md) | Kakao 내부 평점 API 및 Google Places 실험 결과 |
| [kakao-rating-api-walkthrough.html](kakao-rating-api-walkthrough.html) | Kakao 내부 평점 API 조사·재현 명령을 따라하는 HTML 가이드 |

## 현재 상태 (2026-11-25)

- 웹앱: 장소 1,229곳 (미쉐린 168, 서울미래유산 63, 착한가격업소 1,002). 모범음식점은 원본 미확보로 0건. 로컬(localhost:3000)에서 동작 확인.
- 미쉐린 매칭: high 174/180. 나머지 6곳은 보류 (D-026). 음식점이 아닌 Kakao 카테고리로 이름 매칭된 서울미래유산 16건은 수동 확인 전까지 medium으로 내려 웹 데이터에서 제외했습니다 (D-040).
- 미쉐린 데이터: 커뮤니티 크롤러(ngshiheng/michelin-my-maps)가 만든 CSV를 raw URL로 내려받아 사용. 업스트림 커밋 `15ef8a5` (2026-11-03 기준), 우리 다운로드 2026-11-09. 자세한 내용은 data-sources.md 참조.
- 데이터 점수 전략과 외부 소스 실현 가능성 조사: [scoring-strategy.md](scoring-strategy.md). 착한가격업소 1,002건은 주소 검증 매칭 완료. 모범음식점은 공식 원본 CSV 확보 후 연결 예정.
- 웹 UI의 `Matdoria's Pick` v2.1은 Kakao Review ≥50, Kakao Star ≥3.5, Google Review ≥250, Google Star ≥4.0을 모두 충족하는 58곳을 표시합니다. 기존 snapshot 기준으로 count 또는 별점 정보가 없으면 판정 불가로 제외하며 낮은 품질로 해석하지 않습니다 (D-043).
- K Star/G Star 평점 스냅샷을 `places.json`에 포함해 런타임 API 호출 없이 상세와 리스트에 표시합니다. 모바일 리스트 패널은 `peek`/`split`/`expanded` 3단계로 swipe·wheel·손잡이 조작 전환하고, 장소 선택 시 패널 상세로 바꿉니다. K/G Star는 리스트 우측 열에 정렬합니다.
- Google 수집 파일은 기존 high 매칭 253건까지 보충 완료 (238건 100m 이내, 15건 far). 현재 export JSON 1,229곳 중 Google snapshot은 211개, Kakao 평점은 222개입니다. 착한가격업소 추가 1,002곳에는 별도 Google snapshot을 연결하지 않았습니다. 제외된 medium 매칭은 앱 export에 포함하지 않습니다. D-032의 원래 수집 시점 수치는 결정 기록을 참고하세요.
- 현재 앱 runtime에는 Google/Kakao rating API 호출이 없으므로 Vercel에는 `GOOGLE_PLACES_API_KEY`를 등록할 필요가 없습니다. 새 snapshot을 로컬에서 수집할 때만 Google API 키가 필요합니다.
- 백년가게 공식 공개 CSV(1,511행, 2026-08-20 snapshot)를 확보했고, 서울 일반음식점 인허가 데이터도 540,008행 수집·정규화했습니다. 이름+주소가 정확히 일치한 681곳(663 영업/정상, 18 폐업)은 repository 내부 분석용으로 보존하며 Kakao 등록 여부를 보완할 정도의 가치는 없어 앱에서는 제거했습니다. 광진구 위생등급 snapshot 191건도 보관하지만 2026년 등급 기준 변경 전 자료이고 canonical place 매치가 없어 앱에서는 쓰지 않습니다. 오프라인 재빌드 `python scripts/export_places.py`는 장소 JSON, score evidence, 내부 입력 해시/변경 이력, 간단한 `build-info.json`을 생성합니다. 앱에는 Pick 마지막 업데이트 시각과 선정 기준만 표시합니다.
- 다음 단계: Google/Kakao Review·Star snapshot 재사용 조건 확인, 100년가게의 음식점 분류·장소 매칭 검수, 서울미식 100선의 명시적 재사용 허가 확인, Vercel 배포 설정 (Root Directory `web`, 환경변수, 카카오 도메인 등록).
- 보안: 카카오 REST/JS 키와 도로명주소 승인키가 대화에 노출되었으므로 재발급을 권장한다.

## 업데이트 규칙

- 결정이 생기면 `decisions.md`에 `D-NNN` 항목을 추가합니다. 기존 항목은 수정하지 않고, 바뀌면 새 항목으로 "대체됨"을 표시합니다.
- 데이터 소스를 추가하거나 상태가 바뀌면 `data-sources.md`를 갱신합니다.
- 미결 사항은 `requirements.md`의 "미결 사항" 섹션에 둡니다.
- 수집 스크립트를 실행하면 `data/processed/`가 갱신됩니다. 실행 날짜는 CSV의 `fetched_at` 또는 `source_snapshot` 열에 남습니다.
