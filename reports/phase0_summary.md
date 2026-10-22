# Phase 0 — 요약 및 결정 사항

상세 수치: `reports/phase0_exploration.md` (`pipeline/explore.py`가 생성).
데이터: `monthly_processed_data` 2026-07 ~ 2026-09 (94일, 4,405만 행).

## 핵심 발견

1. **스키마**: HANDOFF의 17개 컬럼은 모두 존재. 추가 컬럼 6개
   (`xml_station_name`, `is_additional_stop`, `is_replacement_train`, `replaced_train_type`,
   `replaced_train_number`, `has_plan_record`). 타임스탬프 타입은 `TIMESTAMP_NS`.
2. **`train_line_ride_id`는 운행 1회가 아니라 매일 반복되는 시간표 패턴 ID.**
   운행 1회 = `id`에서 끝의 정차 번호를 뗀 값 (`<ride_id>-<YYMMDDHHMM 첫 출발>-<정차번호>`).
   코리도어 정의도 이 `ride_key` 기준으로 함.
3. **`delay_in_min`은 출발 기준** (출발 시각이 없는 종착 정차만 도착 기준).
   HANDOFF §5.1의 "도착 기준"을 따르려면 `arrival_change_time − arrival_planned_time`을 직접 계산해야 함.
4. **`has_plan_record = false` 행(2.6%)은 계획 시각·지연·열차종류가 모두 null** → 집계에서 제외.
5. **Frankfurt Hbf EVA는 2개**: `08000105`(지상: ICE/RE/RB 등), `08098105`(지하 S-Bahn).
   둘 다 `frankfurt_hbf`로 묶음.
6. **역 이름 차이**: `Neu Isenburg`(하이픈 없음), `Langen (Hess)`.

## 코리도어 노선 (Frankfurt Hbf ↔ Darmstadt Hbf, 일평균 운행)

| 노선 | 일평균 | 정차 |
|---|---|---|
| **S6** | 58.7 | 코리도어 11개 역 전부 (Frankfurt Hbf는 지하 08098105) |
| **RB68** | 37.1 | Frankfurt Hbf · Langen · Darmstadt Hbf |
| **RE60** | 32.1 | Frankfurt Hbf · Langen · Darmstadt Hbf |
| **ICE** | 19.4 | Frankfurt Hbf · Darmstadt Hbf (논스톱) |
| RB67 | 1.3 | DA→FFM만 |
| 기타 (VIA RB61/RB82, IC 등) | < 1 | 무시 가능 |

⚠️ HANDOFF가 예상한 **S3/S4는 이 기간 코리도어에 없음** — 데이터상 S-Bahn은 S6.

## Sanity check — Frankfurt Hbf (취소 제외, 출발 기준 `delay_in_min`)

| | ≥6분 | ≥15분 | ≥30분 | 취소율 |
|---|---|---|---|---|
| 지상 (08000105) | 32.4% | 13.8% | 5.2% | 5.7% |
| 지하 S-Bahn (08098105) | 17.3% | 4.2% | 0.7% | 4.3% |
| **전체** | **26.0%** | 9.8% | 3.3% | 5.1% |

✅ 상식 범위(20~45%) 안. ICE 51%, RE 31%, RB 22%, S 17%로 열차 종류별 순서도 상식적.

## Phase 1에서 정할 것

- **대체 운행**(`is_replacement_train`): 원 열차의 취소로 볼지, 별도 운행으로 볼지. 기본안 = 별도 운행으로 보고 원 열차는 취소로 집계.
- **임시 정차**(`is_additional_stop`): 예보 셀에서 제외 (기본안).
- **지연 기준**: 중간역은 도착 기준으로 직접 계산, 출발역(Frankfurt Hbf 출발 / Darmstadt Hbf 출발)은 출발 기준.
- **학습 기간**: 지금은 3개월. 백테스트를 하려면 더 길게 받아야 함 (예: 2025-11 이후 전체 역 데이터 11개월).

## 슬림 캐시

`data/slim/data-YYYY-MM.parquet` — 대상 12개 EVA만, 월 ~3 MB (원본 ~355 MB).
