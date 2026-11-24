# Seoul restaurant license data acquisition audit

**Facts updated:** 2026-11-24
**Data.go.kr record:** [15071760 — 서울특별시_일반음식점 인허가 정보](https://www.data.go.kr/data/15071760/fileData.do)
**Official Seoul source:** [Seoul Open Data Plaza OA-16094](https://data.seoul.go.kr/dataList/OA-16094/S/1/datasetView.do)

## Official source, freshness, and reuse

Data.go.kr record 15071760 links to the official Seoul Open Data Plaza dataset OA-16094. The Data.go.kr page is an official catalog entry, but it does not host the current data as a direct file: its shortcut opens the Seoul dataset page. That page identifies Seoul Metropolitan Government as provider and the original source as the public Local Administrative Licensing Information system. It offers CSV export for the full dataset; its sheet preview is limited to 1,000 records. The separate attachment table currently says no files are listed.

The Data.go.kr record has an old title suffix (`20200715`), shows modified date `2025-08-08`, and labels its update cycle “수시 (1회성 데이터).” The linked live Seoul page is the freshness reference: it shows daily refresh, data updated `2026-11-22`, and metadata updated `2026-11-23`. The Seoul page says the data is three days old. These source-level notes should not be read as a guarantee that every individual business record has been updated recently.

**Reuse terms:** Data.go.kr states **공공저작물 제1유형 (출처표시 / KOGL Type 1)**. The linked Seoul page says “이용허락범위 제한 없음.” Follow the explicit Type 1 attribution requirement: it allows commercial use and modification with attribution. See the [official KOGL Type 1 terms](https://www.kogl.or.kr/info/licenseType1.do).

## Acquired data and publication state

The collector acquired the official CSV snapshot; no API was called for this acquisition.

| Item | Verified state |
|---|---|
| Raw snapshot | `data/raw/seoul_restaurant_licenses/2026-11-23/seoul_restaurant_licenses_20261122.csv` |
| Raw file | Approximately **215 MB**, **CP949** encoding |
| Parsed content | **540,008 non-empty rows**, **46 source fields** |
| `영업상태명` counts | `폐업`: **419,931**; `영업/정상`: **120,077** |
| Raw snapshot visibility | **Private**; this raw file is not the published app artifact |
| Normalized projection | `data/processed/seoul_restaurant_licenses.csv.gz`, 540,008 rows × 24 selected columns, 36,188,339 bytes; status/date/address/business-type and source provenance retained |
| Exact local matches | `data/processed/seoul_restaurant_licenses_matched.csv`: 702 source records across 681 unique canonical places (exact normalized business name + road address) |
| Review queue | `data/processed/seoul_restaurant_licenses_match_review.csv`: 16,722 name/address candidate rows; 522,584 records had no candidate and remain in the raw/normalized source |
| Internal exact matches | 681 canonical places from 702 license records; 663 resolve to `영업/정상`, 18 to `폐업`. These matches are kept for repository-only analysis. |
| App/Pick use | Removed from the app because Kakao presence is the more relevant user-facing availability check. Administrative status does **not** affect Pick selection. |

The tracked normalized projection is distinct from the private raw snapshot: it is a selected-field, compressed representation, not a copy of the full 215 MB source CSV.

## Analysis scope and caveats

The source supports filtering by administrative operating status and estimating a license-record age. Relevant field families include status name/code (including detailed status), permit date, closure date, address, and business type. **Permit date measures the current license record, not continuous business age.** It does not establish that the business has operated continuously at the same premises or under the same owner. Any “operating years” figure must be labeled as a permit-date estimate, and status values should be treated as administrative status rather than real-time confirmation that the premises is open to customers.

## Hygiene data and national API: separate, not integrated

- [Data.go.kr 15112215 — Gwangjin-gu hygiene-grade establishments](https://www.data.go.kr/data/15112215/fileData.do) has **191 non-empty rows** after skipping **1,008,009 empty placeholders**. It is a `2025-12-31` snapshot using the former three-grade scheme. It predates the **2026-03-16** change to the single `적합` designation, so its grade labels are historical and should not be treated as current labels.
- No exact verified match was found between those hygiene records and the current canonical restaurant places. One same-address record with a different business name was rejected as a match. **Do not claim hygiene data is integrated into the app.**
- [MFDS national food-service hygiene OpenAPI 15060883](https://www.data.go.kr/data/15060883/openapi.do) exists, but it requires its **own Data.go.kr service key**, which is not present in `.env`. **Do not call this API** unless a separate authorized key is provisioned. It has not been called and is not app-integrated.

These are separate sources and states: the acquired Seoul licensing CSV, its compact normalized projection and verified exact-match app signal, the private raw snapshot, the unintegrated Gwangjin hygiene snapshot, and the uncalled national MFDS API.
