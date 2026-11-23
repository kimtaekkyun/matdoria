# Seoul Gourmet 100 (서울미식 100선) source and reuse audit

**Audited:** 2026-11-23 UTC
**Decision:** Do not collect or redistribute the list in this repository yet.

## Official source identified

- **Current official list page (Visit Seoul / Taste of Seoul):** <https://tasteofseoul.visitseoul.net/restaurants/list>
- **Official site's terms of use:** <https://tasteofseoul.visitseoul.net/doc/policy>
- **Official Seoul Open Data Plaza dataset search:** <https://data.seoul.go.kr/dataList/datasetList.do?datasetKind=1&searchFlag=M>
- **Official Data.go.kr dataset search:** <https://www.data.go.kr/tcs/dss/selectDataSetList.do?keyword=%EC%84%9C%EC%9A%B8%EB%AF%B8%EC%8B%9D%20100%EC%84%A0>

The Taste of Seoul page identifies itself as “2026 서울미식 100선” and says it is a Seoul dining guide selected by 60 domestic and international food experts. Its rendered page reports **100 locations**. It is an HTML listing with category and district filters and pagination (pages 1–9); individual entries link to detail pages. The rendered list includes fields such as category, business name, address, phone, and business hours. This is a public presentation page, not a bulk structured-data download or documented API.

## Bulk data and terms check

- An exact-title/keyword search on **Data.go.kr** returned **0 datasets** (0 file datasets and 0 Open APIs).
- Searches for “서울미식 100선”, “서울미식”, and “Seoul Gourmet 100” on **Seoul Open Data Plaza** returned no public-data or statistics results.
- The Taste of Seoul 2026 homepage is <https://tasteofseoul.visitseoul.net/>. Its catalogue link points to an official PDF named `tasteofseoul_2026_홈페이지.pdf` (the link metadata is public); this is a publication/catalogue, not a documented machine-readable data export. No PDF or list file was downloaded.
- The 2026 Seoul Government announcement <https://opengov.seoul.go.kr/press/37099090> says the 100-place selection spans seven categories. Its use-condition field directs users to follow the originating agency's terms and consult the responsible department.
- Seoul's copyright guidance <https://www.seoul.go.kr/helper/copyright.do> says works without a KOGL license mark require prior consultation. A prior-year 2025 Seoul Gourmet 100 page showed KOGL Type 4, but that license must not be assumed to apply to the 2026 work.
- The page does not state an open-data license or permission to extract and redistribute the 2026 list.
- The official Taste of Seoul terms do not grant open reuse. **Article 13(1)(2)** prohibits using information obtained through the service by copying, publishing, broadcasting, or otherwise using it, or providing it to a third party, for commercial **or non-commercial** purposes **without the company’s prior approval**. The official page footer also says “© Taste Of Seoul ALL RIGHT RESERVED.” The public PDF link does not supersede this condition.

Thus, although the official page makes the list viewable and catalogue download links are present, neither a bulk list/API with explicit open reuse terms nor permission to reproduce the list was established. The terms make prior approval a concrete prerequisite. Public visibility and downloadable presentation materials do not themselves authorize bulk extraction or redistribution.

## Acquisition outcome

**No list records, catalogue PDF, or API response was acquired or stored.** The audit verified the official page, catalogue-link metadata, portal searches, and reuse terms only; it did not traverse list pages or extract restaurant records. Consequently, there is no raw snapshot, normalized CSV, fetch script, or acquired data-row count to report. The official page's displayed count of 100 locations is a page claim, not an acquired or independently counted dataset.

The blocker is the absence of an explicit current open license or written prior approval for copying and redistribution under the site's terms. Before acquisition, request written reuse permission from the Seoul Tourism Organization / Taste of Seoul operator, or obtain a current Data.go.kr/Seoul Open Data Plaza record that explicitly authorizes reuse. If permission is granted, preserve the permission evidence and exact source/version before implementing a repeatable collector.
