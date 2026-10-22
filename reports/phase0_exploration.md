# Phase 0 — 데이터 탐색 결과

생성: 2026-10-22 14:54 · 파일: `data-2026-07.parquet`, `data-2026-08.parquet`, `data-2026-09.parquet`

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

- 전체 행: 44,050,509 · 계획 시각 범위: 2026-06-30 21:35:00 ~ 2026-10-01 00:32:00

### delay_in_min 정의 확인
- 결론: 출발 시각이 있으면 출발 기준, 없으면(종착) 도착 기준. 도착 기준 지연은 `arrival_change_time − arrival_planned_time`으로 직접 계산해야 함.
- `delay_in_min == time − arrival_planned_time` 일치율: 46.8%
- `delay_in_min == time − departure_planned_time` 일치율: 100.0%
- `delay_in_min` null 비율: 1.2%

## 2. 역 검색 → EVA 확정

| key | pattern | station_name | eva | rows |
|---|---|---|---|---|
| frankfurt_hbf | Frankfurt (Main) Hbf% | Frankfurt (Main) Hbf | 08000105 | 100,709 |
| frankfurt_hbf | Frankfurt (Main) Hbf% | Frankfurt (Main) Hbf | 08098105 | 72,462 |
| frankfurt_sued | Frankfurt (Main) S_d% | Frankfurt (Main) Süd | 08002041 | 63,090 |
| frankfurt_louisa | Frankfurt%Louisa% | Frankfurt-Louisa | 08002047 | 12,994 |
| neu_isenburg | Neu%Isenburg% | Neu Isenburg | 08004246 | 16,121 |
| dreieich_buchschlag | Dreieich%Buchschlag% | Dreieich-Buchschlag | 08001236 | 18,681 |
| langen | Langen (Hess% | Langen (Hess) | 08003523 | 19,936 |
| egelsbach | Egelsbach% | Egelsbach | 08001672 | 7,911 |
| erzhausen | Erzhausen% | Erzhausen | 08001864 | 7,911 |
| darmstadt_wixhausen | Darmstadt%Wixhausen% | Darmstadt-Wixhausen | 08006528 | 7,911 |
| darmstadt_arheilgen | Darmstadt%Arheilgen% | Darmstadt-Arheilgen | 08001378 | 7,912 |
| darmstadt_hbf | Darmstadt Hbf% | Darmstadt Hbf | 08000068 | 30,972 |

## 3. 코리도어 운행 (같은 운행(ride_key)이 Frankfurt Hbf + Darmstadt Hbf 모두 경유)

| train_type | line_number (장거리는 train_type) | FFM→DA | DA→FFM | 운행 수 | 일평균 |
|---|---|---|---|---|---|
| S | S6 | 2754 | 2761 | 5515 | 58.7 |
| RB | RB68 | 1782 | 1705 | 3487 | 37.1 |
| RE | RE60 | 1512 | 1510 | 3022 | 32.1 |
| ICE | ICE | 879 | 947 | 1826 | 19.4 |
| RB | RB67 | 0 | 124 | 124 | 1.3 |
| ? | S6 | 49 | 45 | 94 | 1.0 |
| ? | RB68 | 41 | 28 | 69 | 0.7 |
| VIA | RB61 | 0 | 65 | 65 | 0.7 |
| ? | RE60 | 15 | 9 | 24 | 0.3 |
| VIA | RB82 | 13 | 0 | 13 | 0.1 |
| ? | ? | 11 | 1 | 12 | 0.1 |
| IC | IC | 0 | 2 | 2 | 0.0 |
| ? | RB82 | 1 | 0 | 1 | 0.0 |
| Bus | RB67 | 0 | 1 | 1 | 0.0 |
| DZ | DZ | 0 | 1 | 1 | 0.0 |

- 기간 내 날짜 수: 94

### 노선 × 역 정차 (일평균 코리도어 운행, 계획 정차만)

| 역 | S6 | RB68 | RE60 | ICE | RB67 |
|---|---|---|---|---|---|
| Frankfurt (Main) Hbf (08000105) | 0.0 | 37.0 | 32.1 | 17.1 | 1.3 |
| Frankfurt (Main) Hbf (08098105) | 58.7 | 0.0 | 0.0 | 0.0 | 0.0 |
| Frankfurt (Main) Süd (08002041) | 58.7 | 0.0 | 0.0 | 0.0 | 0.0 |
| Frankfurt-Louisa (08002047) | 58.7 | 0.0 | 0.0 | 0.0 | 0.0 |
| Neu Isenburg (08004246) | 58.7 | 0.0 | 0.0 | 0.0 | 0.0 |
| Dreieich-Buchschlag (08001236) | 58.7 | 0.0 | 0.0 | 0.0 | 0.0 |
| Langen (Hess) (08003523) | 58.7 | 37.0 | 32.1 | 0.0 | 1.3 |
| Egelsbach (08001672) | 58.7 | 0.0 | 0.0 | 0.0 | 0.0 |
| Erzhausen (08001864) | 58.7 | 0.0 | 0.0 | 0.0 | 0.0 |
| Darmstadt-Wixhausen (08006528) | 58.7 | 0.0 | 0.0 | 0.0 | 0.0 |
| Darmstadt-Arheilgen (08001378) | 58.7 | 0.0 | 0.0 | 0.0 | 0.0 |
| Darmstadt Hbf (08000068) | 58.7 | 37.0 | 32.1 | 17.2 | 1.3 |

### 코리도어 운행이 정차하는 후보 역

| station_name | eva | 코리도어 운행 수 |
|---|---|---|
| Darmstadt Hbf | 08000068 | 14256 |
| Langen (Hess) | 08003523 | 12335 |
| Frankfurt (Main) Hbf | 08000105 | 8647 |
| Dreieich-Buchschlag | 08001236 | 5674 |
| Frankfurt (Main) Süd | 08002041 | 5616 |
| Neu Isenburg | 08004246 | 5610 |
| Frankfurt (Main) Hbf | 08098105 | 5609 |
| Frankfurt-Louisa | 08002047 | 5609 |
| Darmstadt-Wixhausen | 08006528 | 5608 |
| Egelsbach | 08001672 | 5608 |
| Darmstadt-Arheilgen | 08001378 | 5608 |
| Erzhausen | 08001864 | 5608 |

## 4. Sanity check — Frankfurt Hbf 지연률

| eva | n | ≥6분 | ≥15분 | ≥30분 | 취소율 |
|---|---|---|---|---|---|
| 08000105 | 100,709 | 32.4% | 13.8% | 5.2% | 5.7% |
| 08098105 | 72,462 | 17.3% | 4.2% | 0.7% | 4.3% |
| 전체 | 173,171 | 26.0% | 9.8% | 3.3% | 5.1% |

- 판정: ✅ 상식 범위(20~45%)

### train_type별 (취소 제외)

| train_type | n | ≥6분 |
|---|---|---|
| S | 74,562 | 16.7% |
| ICE | 21,281 | 51.0% |
| RE | 20,031 | 30.8% |
| RB | 19,287 | 22.2% |
| HLB | 11,035 | 21.6% |
| VIA | 10,512 | 36.4% |
| vlx | 3,149 | 45.4% |
|  | 2,221 | – |
| TGV | 558 | 40.5% |
| ECE | 491 | 55.2% |
| STN | 396 | 14.1% |
| IC | 332 | 56.6% |
| Bus | 325 | 0.0% |
| NJ | 158 | 63.3% |
| DZ | 5 | 80.0% |

