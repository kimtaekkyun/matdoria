# matdoria 문서

개인 맛집 지도 프로젝트 문서 모음입니다. 요구사항과 결정사항은 여기에 기록하고, 결정이 바뀌면 `decisions.md`에 새 항목을 추가합니다.

| 문서 | 내용 |
|---|---|
| [requirements.md](requirements.md) | 요구사항과 범위 |
| [decisions.md](decisions.md) | 결정 기록 (날짜별, 번호 부여) |
| [data-sources.md](data-sources.md) | 데이터 소스 카탈로그와 상태 |
| [pipeline.md](pipeline.md) | 수집, 매칭, 점수화, export 절차, 배포 |
| [scoring-strategy.md](scoring-strategy.md) | DB 구조, 점수 전략, 외부 데이터 소스 실현 가능성 조사 |
| [rating-api-experiment.md](rating-api-experiment.md) | Kakao 내부 평점 API 및 Google Places 실험 결과 |
| [kakao-rating-api-walkthrough.html](kakao-rating-api-walkthrough.html) | Kakao 내부 평점 API 조사·재현 명령을 따라하는 HTML 가이드 |

## 현재 상태 (2026-11-13)

- 웹앱: 장소 243곳 (미쉐린 168, 서울미래유산 79). 로컬(localhost:3000)에서 동작 확인.
- 미쉐린 매칭: high 174/180. 나머지 6곳은 보류 (D-026).
- 미쉐린 데이터: 커뮤니티 크롤러(ngshiheng/michelin-my-maps)가 만든 CSV를 raw URL로 내려받아 사용. 업스트림 커밋 `15ef8a5` (2026-11-03 기준), 우리 다운로드 2026-11-09. 자세한 내용은 data-sources.md 참조.
- 데이터 점수 전략과 외부 소스 실현 가능성 조사: [scoring-strategy.md](scoring-strategy.md). 착한가격업소 CSV를 확보했으나 현재 장소와의 확정 매칭은 없음. 모범음식점 원본 다운로드와 추가 목록 검증은 후속 작업.
- 웹 UI에 출처별 탭과 `Matdoria's Pick` 탭을 추가했습니다. 아직 데이터/매칭이 없는 탭은 건수 0과 준비 상태 안내를 보여줍니다. Pick 조건 설정은 `data/curation/matdoria_pick.json`에서 시작하며 현재 미선정입니다.
- K Star/G Star 평점 스냅샷을 `places.json`에 포함해 런타임 API 호출 없이 상세와 리스트에 표시합니다. PC는 선택 pin 옆 말풍선, 모바일은 swipe-up 가능한 리스트 패널과 그 안의 상세 화면을 사용합니다. 별점/리뷰 수 기준 정렬도 지원합니다.
- Google 수집 파일은 high 매칭 253건까지 보충 완료 (238건 100m 이내, 15건 far); 통합 장소에 자동 연결한 Google snapshot 222개. Kakao snapshot은 243개 중 236개 평점 확보, 7개는 평점 없음. export 결과는 `web/public/data/places.json`에서 확인합니다. D-032 참고.
- 현재 앱 runtime에는 Google/Kakao rating API 호출이 없으므로 Vercel에는 `GOOGLE_PLACES_API_KEY`를 등록할 필요가 없습니다. 새 snapshot을 로컬에서 수집할 때만 Google API 키가 필요합니다.
- 다음 단계: 외부 데이터의 실제 파일/커버리지 검증 및 Vercel 배포 (Root Directory `web`, 환경변수, 카카오 도메인 등록).
- 보안: 카카오 REST/JS 키와 도로명주소 승인키가 대화에 노출되었으므로 재발급을 권장한다.

## 업데이트 규칙

- 결정이 생기면 `decisions.md`에 `D-NNN` 항목을 추가합니다. 기존 항목은 수정하지 않고, 바뀌면 새 항목으로 "대체됨"을 표시합니다.
- 데이터 소스를 추가하거나 상태가 바뀌면 `data-sources.md`를 갱신합니다.
- 미결 사항은 `requirements.md`의 "미결 사항" 섹션에 둡니다.
- 수집 스크립트를 실행하면 `data/processed/`가 갱신됩니다. 실행 날짜는 CSV의 `fetched_at` 또는 `source_snapshot` 열에 남습니다.
