# matdoria 문서

개인 맛집 지도 프로젝트 문서 모음입니다. 요구사항과 결정사항은 여기에 기록하고, 결정이 바뀌면 `decisions.md`에 새 항목을 추가합니다.

| 문서 | 내용 |
|---|---|
| [requirements.md](requirements.md) | 요구사항과 범위 |
| [decisions.md](decisions.md) | 결정 기록 (날짜별, 번호 부여) |
| [data-sources.md](data-sources.md) | 데이터 소스 카탈로그와 상태 |
| [pipeline.md](pipeline.md) | 수집, 매칭, 점수화, export 절차, 배포 |

## 현재 상태 (2026-11-10)

- 웹앱: 장소 243곳 (미쉐린 168, 서울미래유산 79). 로컬(localhost:3000)에서 동작 확인.
- 미쉐린 매칭: high 174/180. 나머지 6곳은 보류 (D-026).
- 미쉐린 데이터: 커뮤니티 크롤러(ngshiheng/michelin-my-maps)가 만든 CSV를 raw URL로 내려받아 사용. 업스트림 커밋 `15ef8a5` (2026-11-03 기준), 우리 다운로드 2026-11-09. 자세한 내용은 data-sources.md 참조.
- 다음 단계: Vercel 배포 (Root Directory `web`, 환경변수, 카카오 도메인 등록).
- 보안: 카카오 REST/JS 키와 도로명주소 승인키가 대화에 노출되었으므로 재발급을 권장한다.

## 업데이트 규칙

- 결정이 생기면 `decisions.md`에 `D-NNN` 항목을 추가합니다. 기존 항목은 수정하지 않고, 바뀌면 새 항목으로 "대체됨"을 표시합니다.
- 데이터 소스를 추가하거나 상태가 바뀌면 `data-sources.md`를 갱신합니다.
- 미결 사항은 `requirements.md`의 "미결 사항" 섹션에 둡니다.
- 수집 스크립트를 실행하면 `data/processed/`가 갱신됩니다. 실행 날짜는 CSV의 `fetched_at` 또는 `source_snapshot` 열에 남습니다.
