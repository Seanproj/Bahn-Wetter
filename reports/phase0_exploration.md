# Phase 0 — 데이터 탐색 결과

생성: 2026-10-23 11:02 · 파일: `data-2025-11.parquet`, `data-2025-12.parquet`, `data-2026-01.parquet`, `data-2026-02.parquet`, `data-2026-03.parquet`, `data-2026-04.parquet`, `data-2026-05.parquet`, `data-2026-06.parquet`, `data-2026-07.parquet`, `data-2026-08.parquet`, `data-2026-09.parquet`

## 1. 실제 스키마

| column | type |
|---|---|
| station_name | VARCHAR |
| xml_station_name | VARCHAR |
| eva | VARCHAR |
| train_number | VARCHAR |
| line_number | VARCHAR |
| final_destination_station | VARCHAR |
| delay_in_min | INTEGER |
| time | TIMESTAMP_NS |
| arrival_is_canceled | BOOLEAN |
| departure_is_canceled | BOOLEAN |
| train_type | VARCHAR |
| is_additional_stop | BOOLEAN |
| is_replacement_train | BOOLEAN |
| replaced_train_type | VARCHAR |
| replaced_train_number | VARCHAR |
| has_plan_record | BOOLEAN |
| train_line_ride_id | VARCHAR |
| train_line_station_num | INTEGER |
| arrival_planned_time | TIMESTAMP_NS |
| arrival_change_time | TIMESTAMP_NS |
| departure_planned_time | TIMESTAMP_NS |
| departure_change_time | TIMESTAMP_NS |
| id | VARCHAR |


- HANDOFF에 있으나 데이터에 없는 컬럼: 없음
- 데이터에 있으나 HANDOFF에 없는 컬럼: ['has_plan_record', 'is_additional_stop', 'is_replacement_train', 'replaced_train_number', 'replaced_train_type', 'xml_station_name']

- 전체 행: 163,404,013 · 계획 시각 범위: 2025-10-31 22:25:00 ~ 2026-10-01 00:32:00

### delay_in_min 정의 확인
- 결론: 출발 시각이 있으면 출발 기준, 없으면(종착) 도착 기준. 도착 기준 지연은 `arrival_change_time − arrival_planned_time`으로 직접 계산해야 함.
- `delay_in_min == time − arrival_planned_time` 일치율: 46.8%
- `delay_in_min == time − departure_planned_time` 일치율: 100.0%
- `delay_in_min` null 비율: 0.9%

## 2. 역 검색 → EVA 확정

| key | pattern | station_name | eva | rows |
|---|---|---|---|---|
| frankfurt_hbf | Frankfurt (Main) Hbf% | Frankfurt (Main) Hbf | 08000105 | 371,106 |
| frankfurt_hbf | Frankfurt (Main) Hbf% | Frankfurt (Main) Hbf | 08098105 | 274,010 |
| frankfurt_sued | Frankfurt (Main) S_d% | Frankfurt (Main) Süd | 08002041 | 234,470 |
| frankfurt_louisa | Frankfurt%Louisa% | Frankfurt-Louisa | 08002047 | 46,953 |
| neu_isenburg | Neu%Isenburg% | Neu Isenburg | 08004246 | 57,700 |
| dreieich_buchschlag | Dreieich%Buchschlag% | Dreieich-Buchschlag | 08001236 | 66,889 |
| langen | Langen (Hess% | Langen (Hess) | 08003523 | 73,607 |
| egelsbach | Egelsbach% | Egelsbach | 08001672 | 28,681 |
| erzhausen | Erzhausen% | Erzhausen | 08001864 | 28,685 |
| darmstadt_wixhausen | Darmstadt%Wixhausen% | Darmstadt-Wixhausen | 08006528 | 28,653 |
| darmstadt_arheilgen | Darmstadt%Arheilgen% | Darmstadt-Arheilgen | 08001378 | 28,682 |
| darmstadt_hbf | Darmstadt Hbf% | Darmstadt Hbf | 08000068 | 114,516 |
| frankfurt_flughafen | Frankfurt (Main) Flughafen Regionalbahnhof% | Frankfurt (Main) Flughafen Regionalbahnhof | 08070004 | 77,298 |
| frankfurt_flughafen | Frankfurt am Main Flughafen Fernbahnhof% | Frankfurt am Main Flughafen Fernbahnhof | 08070003 | 69,871 |
| wiesbaden_hbf | Wiesbaden Hbf% | Wiesbaden Hbf | 08000250 | 128,169 |
| mainz_hbf | Mainz Hbf% | Mainz Hbf | 08000240 | 158,764 |
| hanau_hbf | Hanau Hbf% | Hanau Hbf | 08000150 | 170,160 |

## 3. 코리도어 운행 (같은 운행(ride_key)이 Frankfurt Hbf + Darmstadt Hbf 모두 경유)

| train_type | line_number (장거리는 train_type) | FFM→DA | DA→FFM | 운행 수 | 일평균 |
|---|---|---|---|---|---|
| S | S6 | 10935 | 11086 | 22021 | 65.5 |
| RB | RB68 | 5556 | 5294 | 10850 | 32.3 |
| RE | RE60 | 4592 | 4562 | 9154 | 27.2 |
| ICE | ICE | 3417 | 3514 | 6931 | 20.6 |
| S | 6 | 1844 | 1873 | 3717 | 11.1 |
| RB | 68 | 902 | 851 | 1753 | 5.2 |
| RB | 67 | 818 | 876 | 1694 | 5.0 |
| RE | 60 | 696 | 714 | 1410 | 4.2 |
| RB | RB67 | 0 | 364 | 364 | 1.1 |
| ? | S6 | 162 | 161 | 323 | 1.0 |
| VIA | RB61 | 0 | 217 | 217 | 0.6 |
| IC | IC | 120 | 94 | 214 | 0.6 |
| ? | RB68 | 104 | 92 | 196 | 0.6 |
| VIA | RB82 | 163 | 10 | 173 | 0.5 |
| ? | RE60 | 37 | 28 | 65 | 0.2 |
| EC | EC | 31 | 31 | 62 | 0.2 |
| RJX | RJX | 25 | 24 | 49 | 0.1 |
| S | S | 16 | 18 | 34 | 0.1 |
| ? | ? | 22 | 7 | 29 | 0.1 |
| ? | 6 | 6 | 5 | 11 | 0.0 |
| Bus | RB82 | 4 | 4 | 8 | 0.0 |
| Bus | SEV | 1 | 7 | 8 | 0.0 |
| RE | RE55 | 6 | 0 | 6 | 0.0 |
| ? | 68 | 3 | 2 | 5 | 0.0 |
| ? | 67 | 2 | 2 | 4 | 0.0 |
| ? | 60 | 1 | 2 | 3 | 0.0 |
| RE | RE54 | 2 | 0 | 2 | 0.0 |
| DZ | DZ | 0 | 1 | 1 | 0.0 |
| RE | 70 | 1 | 0 | 1 | 0.0 |
| Bus | RB67 | 0 | 1 | 1 | 0.0 |
| ? | RB82 | 1 | 0 | 1 | 0.0 |

- 기간 내 날짜 수: 336

### 노선 × 역 정차 (일평균 코리도어 운행, 계획 정차만)

| 역 | S6 | RB68 | RE60 | ICE | 6 |
|---|---|---|---|---|---|
| Frankfurt (Main) Hbf (08000105) | 0.0 | 32.2 | 27.2 | 18.3 | 0.0 |
| Frankfurt (Main) Hbf (08098105) | 65.5 | 0.0 | 0.0 | 0.0 | 11.0 |
| Frankfurt (Main) Süd (08002041) | 65.5 | 0.0 | 0.0 | 0.0 | 11.0 |
| Frankfurt-Louisa (08002047) | 65.5 | 0.0 | 0.0 | 0.0 | 10.4 |
| Neu Isenburg (08004246) | 65.5 | 0.0 | 0.0 | 0.0 | 10.4 |
| Dreieich-Buchschlag (08001236) | 65.5 | 0.0 | 0.0 | 0.0 | 10.4 |
| Langen (Hess) (08003523) | 65.5 | 32.2 | 27.2 | 0.2 | 10.4 |
| Egelsbach (08001672) | 65.5 | 0.0 | 0.0 | 0.0 | 10.4 |
| Erzhausen (08001864) | 65.5 | 0.0 | 0.0 | 0.0 | 10.4 |
| Darmstadt-Wixhausen (08006528) | 65.5 | 0.0 | 0.0 | 0.0 | 10.4 |
| Darmstadt-Arheilgen (08001378) | 65.5 | 0.0 | 0.0 | 0.0 | 10.4 |
| Darmstadt Hbf (08000068) | 65.5 | 32.2 | 27.2 | 18.3 | 11.0 |

### 코리도어 운행이 정차하는 후보 역

| station_name | eva | 코리도어 운행 수 |
|---|---|---|
| Darmstadt Hbf | 08000068 | 59307 |
| Langen (Hess) | 08003523 | 51312 |
| Frankfurt (Main) Hbf | 08000105 | 33201 |
| Frankfurt (Main) Süd | 08002041 | 26162 |
| Dreieich-Buchschlag | 08001236 | 26139 |
| Frankfurt (Main) Hbf | 08098105 | 26106 |
| Neu Isenburg | 08004246 | 25931 |
| Darmstadt-Wixhausen | 08006528 | 25927 |
| Egelsbach | 08001672 | 25927 |
| Erzhausen | 08001864 | 25927 |
| Frankfurt-Louisa | 08002047 | 25924 |
| Darmstadt-Arheilgen | 08001378 | 25923 |
| Hanau Hbf | 08000150 | 23 |
| Frankfurt am Main Flughafen Fernbahnhof | 08070003 | 1 |
| Wiesbaden Hbf | 08000250 | 1 |

## 4. Sanity check — Frankfurt Hbf 지연률

| eva | n | ≥6분 | ≥15분 | ≥30분 | 취소율 |
|---|---|---|---|---|---|
| 08000105 | 371,106 | 30.5% | 13.0% | 4.7% | 5.8% |
| 08098105 | 274,010 | 19.0% | 4.9% | 0.9% | 5.1% |
| 전체 | 645,116 | 25.6% | 9.5% | 3.1% | 5.5% |

- 판정: ✅ 상식 범위(20~45%)

### train_type별 (취소 제외)

| train_type | n | ≥6분 |
|---|---|---|
| S | 283,617 | 18.2% |
| ICE | 78,537 | 47.1% |
| RE | 74,940 | 29.6% |
| RB | 61,132 | 22.7% |
| HLB | 38,855 | 21.5% |
| VIA | 37,948 | 35.6% |
| STN | 12,832 | 9.4% |
| vlx | 8,893 | 41.2% |
|  | 6,368 | – |
| IC | 2,173 | 49.0% |
| TGV | 1,897 | 39.4% |
| ECE | 1,681 | 53.2% |
| Bus | 518 | 0.0% |
| NJ | 320 | 60.6% |
| EC | 61 | 49.2% |

