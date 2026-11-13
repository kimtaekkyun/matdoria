# 평점 API 실험 기록

조사일: 2026-11-13
초기 API 검증과 현재 static snapshot 수집 내역. Kakao 개별 리뷰 본문은 저장하지 않는다.

## 결과 요약

| 플랫폼 | 기술 실험/수집 | 결과 | 현재 제품 사용 |
|---|---|---|---|
| Kakao | 내부 API 단건 검증 후 현재 카카오 장소 243곳을 배치 조회 | 236개 평점 확보, 7개 무평점 | K Star/count snapshot을 `places.json`에 포함. 런타임 API 호출 없음 |
| Google | Places API 단건 검증. high source row 253건을 보충 수집 | 238건 100m 이내, 15건 far, 251개 rating. 통합 지도에는 222개 고유·근접 Google 장소 snapshot만 연결 | G Star/count snapshot을 `places.json`에 포함. 런타임 API 호출 없음 |

**값을 static하게 보관하면 갱신 전까지 오래될 수 있고, Google 콘텐츠 저장 정책과 Kakao 내부 API 사용 권한 위험도 남는다.** 이 구현은 사용자가 static snapshot 방식을 요청해 적용한 것이며, 정책상 허용된다는 보증은 아니다.

## Kakao 내부 API 실험

현재 카카오맵 장소 페이지의 JavaScript 번들에서 다음 요청 패턴을 확인했다.

```text
GET https://place.map.kakao.com/places/tab/reviews/kakaomap/{place_id}
    ?order=RECOMMENDED&only_photo_review=false
```

요청에 사용한 핵심 헤더:

```text
Referer: https://place.map.kakao.com/{place_id}
appVersion: 6.6.0
pf: PC
Accept: application/json, text/plain, */*
```

7th Door (`1147571189`) 테스트 응답의 집계 필드:

```json
{
  "score_set": {
    "review_count": 17,
    "total_score": 71,
    "average_score": 4.2
  }
}
```

- 응답에는 집계 필드 외에 리뷰 객체도 포함된다. 실험에서는 리뷰 본문을 기록하거나 사용하지 않았다.
- 정렬값은 `RECOMMENDED` 또는 `LATEST`; 임의의 `recent`는 HTTP 400이었다.
- 이는 공식 Local API가 아니라 카카오맵 웹앱의 undocumented 내부 엔드포인트다. URL, 필수 헤더, 응답 스키마, 호출 허용량은 언제든 바뀔 수 있다.
- 이전 실험의 추정 API 경로들은 오래된 번들 기준이었고 현재 작동하지 않았다. 현재 번들에서 실제 경로를 찾은 뒤 한 번의 집계 요청이 성공한 것이다.
- 이 실험만으로 자동화 수집, 캐싱, 재배포, 배포 웹앱에서 호출하는 행위가 허용된다고 볼 수 없다.

## Google Places API 실험

기존 샘플 스크립트 `scripts/sample_google_ratings.py`를 1건 실행했다. FieldMask는 Places API(New)의 `rating`, `userRatingCount`를 포함했고 7th Door에 대해 평점 4.6, 평가 수 128, 카카오 좌표와의 거리 1m를 반환했다.

공식 정책 확인 링크:

- [Places API policies](https://developers.google.com/maps/documentation/places/web-service/policies)
- [Places API data fields](https://developers.google.com/maps/documentation/places/web-service/data-fields)

정책은 Places 콘텐츠의 저장/캐싱과 파생 콘텐츠 생성을 제한하고, Places 결과를 지도에 표시할 때 Google 지도를 요구한다. 사용자의 요청으로 Google snapshot을 `places.json`에 넣었지만, 이것은 **약관 적합성 판단이나 Google의 허가를 뜻하지 않는다.** Google 평점은 Matdoria's Pick 점수에 사용하지 않는다. 배포된 앱은 이 snapshot을 읽을 뿐 Google API를 호출하지 않는다.

## 현재 static snapshot 구조

- `scripts/fetch_kakao_ratings.py`: `places.json`의 Kakao ID를 대상으로 내부 API에 요청하고 `average_score`, `review_count`만 `data/processed/kakao_ratings.csv`에 보관한다. 리뷰 내용은 파일에 쓰지 않는다.
- Google snapshot: `data/raw/google/ratings.csv`의 source row → Google Place ID/평점 정보를 검증한 뒤 export에 사용한다. `scripts/fetch_google_ratings.py`는 Google Place ID가 없는 신규 source row를 찾을 때 Google Places API 키를 사용한다.
- `scripts/export_places.py`는 수집 결과를 `ratings.kakao`와 `ratings.google` snapshot으로 `places.json`에 넣는다. `PlaceDetail`과 리스트는 이 JSON만 읽으며 외부 평점 API를 호출하지 않는다.
- Google Place ID와 Google rating/count를 static JSON에 포함한다. Kakao rating/count도 동일하게 snapshot으로 포함하며, 각 항목의 수집 시각을 보존한다. 데이터가 없는 플랫폼은 빈 snapshot으로 두어 UI 정렬에서 뒤로 보낸다.
- `PlaceDetail`과 리스트는 `places.json`만 읽고 외부 평점 API를 호출하지 않는다. Kakao/Google 지도 보기 버튼도 일반 URL이므로 Google Places API 키가 필요 없다.
- Google Place ID는 기존 확인 자료에서 source 좌표 100m 이내인 `ok` 매칭만 사용한다. 같은 Kakao 장소에 여러 Google ID가 충돌하면 임의로 고르지 않는다. 현재 222개만 자동 연결됐고, 21개는 far/충돌로 미연결이다.
- `data/raw/google/ratings.csv`는 평점/평가 수를 포함한 Git 추적 파일이며 201행에서 253행으로 갱신됐다. Google 콘텐츠의 정적 저장 정책 위험은 남아 있으므로 파일/JSON 공개 여부를 운영자가 인지해야 한다.
- Google API 키는 batch 수집 시 루트 `.env.local`에서 사용한다. Vercel 웹앱 runtime에는 전달하지 않는다. Matdoria's Pick 점수에는 평점을 포함하지 않는다.

## Google 수집 누락분 보충 결과

`python scripts/fetch_google_ratings.py`를 다시 실행했다. 이전 캐시 201개에서 high-confidence source row 253개 전체를 처리해 누락 52개를 조회했다. 누락 건은 Google Text Search 결과에서 Place ID와 현재 rating/count를 얻었고, 웹 상세 화면은 확정된 Google Place ID로 Place Details를 호출한다.

- 처리된 source row: 253/253
- Google Place ID가 있는 결과: 253
- 원본 좌표 100m 이내 (`ok`): 238
- 100m 초과 (`far`): 15
- rating 필드가 있는 row: 251
- 웹 JSON에 연결한 Google Place ID: 222개 canonical Kakao 장소
- 나머지 21개는 15개 far 위치 및 서로 다른 Google ID가 동일한 Kakao 장소를 가리키는 충돌로 자동 연결하지 않았다. 오매칭을 피하려고 미해결 상태로 둔다.
