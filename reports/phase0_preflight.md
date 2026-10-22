# Phase 0 — Preflight (데이터 다운로드 전)

상태: **⛔ 데이터 다운로드 차단** — 클라우드 환경 네트워크 정책이 `huggingface.co`를 막고 있음.
아래는 업스트림 저장소(github.com/piebro/deutsche-bahn-data)의 README와
`config/eva_to_station_name.json`에서 확인한 사전 정보이며, **parquet로 재확인 전까지 확정 아님**.
확정 결과는 `pipeline/explore.py`가 `reports/phase0_exploration.md`로 생성한다.

## 1. 스키마 — HANDOFF.md 대비 차이 (업스트림 README 기준)

HANDOFF.md §3.1의 17개 컬럼은 모두 README 스키마에 존재. 추가로 HANDOFF에 없는 컬럼:

| 컬럼 | 도입 | 의미 | 영향 |
|---|---|---|---|
| `xml_station_name` | – | XML 응답의 역 이름 | 없음 |
| `is_additional_stop` | 2026-09 | 계획에 없던 정차 (우회 등) | 예보 셀 집계에서 제외 검토 |
| `is_replacement_train` | 2026-09 | 다른 열차번호로 대체 운행 | 대체 운행을 원 열차의 취소로 볼지 결정 필요 |
| `replaced_train_number` | 2026-09 | 대체된 원 열차번호 | 위와 연계 |
| `replaced_train_type` | 2026-10 | 대체된 원 열차종류 | 위와 연계 |
| `has_plan_record` | 2026-10 | 계획 스냅샷 존재 여부 | `false`면 계획 시각 결측 → 지연 계산 제외 |

또한 2026-10부터 재운행(`cs="p"`) 정류장은 취소로 표시되지 않음. 모든 과거 월 파일이 새 스키마로 재처리됨.

## 2. 후보 역 EVA (업스트림 eva_to_station_name.json 기준)

| key | 데이터상 역 이름 | EVA | 비고 |
|---|---|---|---|
| frankfurt_hbf | Frankfurt (Main) Hbf | 08000105, 08098105 | **EVA 2개** — 08098105는 지하 S-Bahn 승강장으로 추정, 데이터로 확인 필요 |
| frankfurt_sued | Frankfurt (Main) Süd | 08002041 | |
| frankfurt_louisa | Frankfurt-Louisa | 08002047 | |
| neu_isenburg | Neu Isenburg | 08004246 | HANDOFF 표기(Neu-Isenburg)와 다름 — 하이픈 없음 |
| dreieich_buchschlag | Dreieich-Buchschlag | 08001236 | |
| langen | Langen (Hess) | 08003523 | HANDOFF 표기(Langen (Hessen))와 다름 |
| egelsbach | Egelsbach | 08001672 | |
| erzhausen | Erzhausen | 08001864 | |
| darmstadt_wixhausen | Darmstadt-Wixhausen | 08006528 | |
| darmstadt_arheilgen | Darmstadt-Arheilgen | 08001378 | |
| darmstadt_hbf | Darmstadt Hbf | 08000068 | |

11개 후보 모두 매핑에 존재. 검색 패턴은 `config/station_search.yaml`에 반영(EVA 하드코딩 없음).

## 3. 다운로드 후 실행 순서

```bash
uv run python pipeline/download.py --months 3
uv run python pipeline/explore.py     # → reports/phase0_exploration.md, config/stations.yaml
uv run python pipeline/slim.py        # → data/slim/
```
