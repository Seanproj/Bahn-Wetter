# HANDOFF — DB 지연 예보 (Bahn-Wetter) 🌦️🚆

> "오늘 Frankfurt Hbf, 지연 확률 70% — 우산 대신 여유 시간을 챙기세요."
> 날씨 예보 포맷으로 보여주는 Deutsche Bahn 지연 확률 웹. Frankfurt Hbf 중심 + Frankfurt ↔ Darmstadt 출퇴근 구간 특화.

---

## 1. 한 줄 정의
과거 실측 지연 데이터(공개 데이터셋)로 **역 × 노선 × 요일 × 시간대별 지연 확률**을 계산하고, 이를 **날씨 예보 UI(☀️🌤️☁️🌧️⛈️)**로 보여주는 재미 중심 웹.

## 2. 왜 만드나 (포지셔닝)
- 비슷한 진지한 도구는 이미 있음: bahn.expert, next.bahnvorhersage.de, zugspaet.de, delaybahn, railwise, BayesianBahn.
- **차별점 = 포맷과 톤.** 정확도 경쟁이 아니라 "보는 재미 + 공유하고 싶은 카드".
- 한국어 기본 (독일 거주 한국인 대상), 독일어/영어 토글은 후순위.
- 매일 자동 생성되는 "오늘의 DB 예보" 카드 → Instagram(newworldwithmj) / 쇼츠 소재로 재활용.

## 3. 데이터 소스

### 3.1 메인: piebro/deutsche-bahn-data (Hugging Face)
- URL: https://huggingface.co/datasets/piebro/deutsche-bahn-data
- GitHub: https://github.com/piebro/deutsche-bahn-data
- 라이선스: **CC BY 4.0 (Deutsche Bahn)** → 사이트에 출처 표기 필수.
- 원천: DB Timetables API (plan + fchg), 하루 4회 수집.
- 커버리지: 2024-07 ~ 2025-11-02는 주요 ~100개 역만, **2025-11 이후 전체 역** → Darmstadt 구간은 2025-11 이후 데이터 사용.
- 타임스탬프: Europe/Berlin 로컬 시간 (변환 없음).
- 결측: 2026-04(34h), 2026-05(31h), 2026-07(102h) 등 일부 시간대 누락 → 표본 수 계산 시 고려.
- 다운로드 (월별 가공본만):
  ```bash
  uv run --with "huggingface-hub" hf download piebro/deutsche-bahn-data \
    --repo-type=dataset --local-dir=data --include "monthly_processed_data/*"
  ```
- 월별 파일 `monthly_processed_data/data-YYYY-MM.parquet` 주요 컬럼:
  `station_name, eva, train_type, train_number, line_number (장거리는 null), final_destination_station, delay_in_min, arrival_planned_time, arrival_change_time, departure_planned_time, departure_change_time, arrival_is_canceled, departure_is_canceled, train_line_ride_id, train_line_station_num, time, id`
- ⚠️ 스키마 변경 이력: 2026-05에 `train_name` → `train_number` + `line_number` 분리, 2026-08에 `is_canceled` → `arrival_is_canceled` / `departure_is_canceled` 분리. **실제 parquet 스키마를 먼저 확인하고 코드 작성.**

### 3.2 (Phase 2) 실시간: DB API Marketplace Timetables API
- https://developers.deutschebahn.com/db-api-marketplace/apis/product/timetables
- Client ID / API Key 필요 (무료 등록). `.env`로 관리, 절대 커밋 금지.
- 용도: "현재 이미 X분 지연 중" → 과거 분포에 조건부로 반영.

## 4. 범위 (MVP)

### 4.1 대상 역
**Hub:** Frankfurt (Main) Hbf

**Frankfurt ↔ Darmstadt 코리도어** (데이터로 실제 존재 여부 검증 후 확정):
Frankfurt (Main) Hbf · Frankfurt (Main) Süd · Frankfurt-Louisa · Neu-Isenburg · Dreieich-Buchschlag · Langen (Hessen) · Egelsbach · Erzhausen · Darmstadt-Wixhausen · Darmstadt-Arheilgen · Darmstadt Hbf

> 역 이름/EVA 번호는 하드코딩하지 말고 데이터에서 `station_name ILIKE` 검색으로 찾은 뒤 `config/stations.yaml`에 고정.

### 4.2 대상 노선 (후보 — 데이터로 검증)
- S-Bahn: S3, S4 (Darmstadt까지 가는 편만 코리도어로 분류)
- 지역: RE60, RB67, RB68 등 Main-Neckar-Bahn 경유 노선
- 장거리: Darmstadt Hbf 정차 ICE/IC/EC (`line_number` null → `train_type + train_number`로 식별)
- Frankfurt Hbf 허브 페이지는 전체 노선 대상

> **규칙:** 노선 목록도 하드코딩 금지. "Frankfurt Hbf와 Darmstadt Hbf를 같은 `train_line_ride_id`로 모두 지나는 운행"을 코리도어 운행으로 정의하고, 거기서 등장하는 `line_number`/`train_type`을 추출.

## 5. 예보 로직

### 5.1 지연 기준
- DB 공식 정시 기준: **6분 미만 = 정시**. 기본 "지연" = `delay_in_min >= 6`.
- 추가 임계값: ≥15분, ≥30분, 취소율.
- 도착 기준 (`arrival_*`), 출발역은 출발 기준.

### 5.2 확률 계산 (경험적 + 축소 추정)
- 셀(cell) = `역 × 노선(또는 열차번호) × 요일구분(평일/토/일·공휴일) × 시간대(1시간 버킷)`
- `P(delay ≥ 6) = 지연 건수 / 전체 운행 건수` (취소는 별도 집계)
- 표본 부족 대응: **Beta-Binomial 축소** — 상위 레벨(노선 전체 → 역 전체) 비율을 prior로 사용.
  `p̂ = (k + α) / (n + α + β)`, prior 강도 `α + β ≈ 20` 시작, 백테스트로 튜닝.
- 최근성 가중: 최근 4주 가중치 ↑ (지수 감쇠, half-life 약 21일부터 시작).
- n < 10이면 "데이터 부족" 표시 (확률 숨김).

### 5.3 날씨 매핑 (P(≥6분))
| 아이콘 | 확률 | 문구 예시 |
|---|---|---|
| ☀️ | < 15% | 맑음 — 그냥 타세요 |
| 🌤️ | 15–30% | 구름 조금 — 환승 5분은 아슬아슬 |
| ☁️ | 30–45% | 흐림 — 커피 한 잔 여유 |
| 🌧️ | 45–60% | 비 — 다음 열차도 확인 |
| ⛈️ | ≥ 60% | 뇌우 — 중요한 약속이면 한 대 일찍 |
| 🌪️ | 취소율 ≥ 10% | 토네이도 — 열차가 사라질 수 있음 |

임계값은 실제 분포를 보고 조정 (Frankfurt Hbf 전체 평균이 ☁️ 근처에 오도록).

### 5.4 검증 (필수)
- 시간 기준 분할 백테스트: 직전 N개월로 학습 → 다음 1개월 예측.
- 지표: Brier score, 캘리브레이션 그래프 (예측 30% 구간이 실제 ~30% 지연인지).
- 베이스라인 대비: (a) 역 전체 평균, (b) 노선 전체 평균. **베이스라인보다 나아야 의미 있음.**
- 결과를 `reports/backtest.md`에 기록하고 사이트 "예보 정확도" 페이지에 공개 (재미 + 신뢰).

## 6. 화면 구성

1. **홈 — 오늘의 DB 예보 (Frankfurt Hbf)**
   큰 날씨 아이콘 + 오늘 전체 지연 확률, 시간대별 예보 스트립 (06시~23시, 날씨앱처럼 가로 스크롤).
2. **🚆 Darmstadt 출퇴근 예보**
   방향 토글 (FFM → DA / DA → FFM), 시간대 × 노선 그리드 (S3 / RE60 / RB67 / ICE…), 각 칸 = 날씨 아이콘 + %.
   "오늘 아침 가장 맑은 열차" 추천 1개.
3. **열차 상세**
   지연 분포 히스토그램, 요일별 비교, "최악의 날 Top 3" (최대 지연 기록).
4. **🏆 주간 랭킹**
   이번 주 최악의 열차/노선, 가장 성실한 열차 (가장 맑음).
5. **📸 공유 카드**
   1080×1350 PNG (Instagram 세로) — "오늘의 DB 예보 · Frankfurt Hbf" 카드 자동 생성.
6. **ℹ️ About**
   데이터 출처 (CC BY 4.0, Deutsche Bahn / piebro), 비공식 서비스 고지, 방법론 요약.

디자인 톤: 날씨앱 감성 (그라데이션 하늘 배경이 확률에 따라 변화), 모바일 우선, 다크모드.

## 7. 아키텍처 (권장)

```
bahn-wetter/
├── pipeline/            # Python 3.12+, uv
│   ├── download.py      # HF에서 월별 parquet 다운로드 (증분)
│   ├── explore.py       # 역/노선 탐색 → config 생성 보조
│   ├── build_stats.py   # DuckDB 집계 → 확률 테이블
│   ├── backtest.py      # 검증
│   └── export.py        # 정적 JSON 출력 (site/public/data/*.json)
├── config/
│   ├── stations.yaml    # 대상 역 + EVA
│   └── weather.yaml     # 날씨 임계값/문구
├── site/                # 정적 프론트엔드 (Vite + vanilla TS 또는 Astro)
├── cards/               # 공유 카드 PNG 생성 (Playwright 스크린샷 or satori)
├── reports/
├── .github/workflows/   # 주 1회 데이터 갱신 + 배포
└── data/                # gitignore
```

- **백엔드 서버 없음.** 파이프라인이 정적 JSON을 만들고 프론트가 읽음 → GitHub Pages / Cloudflare Pages 무료 배포.
- 집계는 DuckDB로 parquet 직접 쿼리 (전체 로드 X, 대상 역 EVA로 필터).
- 디스크: 월별 가공본은 수백 MB~GB 단위일 수 있음 → 대상 역만 필터링한 slim parquet로 캐시.

## 8. 단계별 계획

| Phase | 목표 | 완료 기준 |
|---|---|---|
| 0 | 데이터 탐색 | 실제 스키마 확인, 코리도어 역/노선 목록 확정, `stations.yaml` 작성 |
| 1 | 통계 + 백테스트 | 확률 테이블 생성, Brier/캘리브레이션이 베이스라인보다 나음 |
| 2 | MVP 웹 | 홈 + Darmstadt 출퇴근 예보 화면, 모바일에서 동작 |
| 3 | 재미 요소 | 주간 랭킹, 공유 카드 PNG, 하늘 배경 애니메이션 |
| 4 | 자동화 | GitHub Actions 주간 갱신 + 배포 |
| 5 | 실시간 (선택) | Timetables API 연동, "현재 지연 반영" 예보 |

## 9. 제약 / 원칙
- 비공식 서비스임을 명시, DB 로고/브랜드 사용 금지 (이름에 "DB" 단독 사용 지양 → "Bahn-Wetter" 등).
- 출처 표기: "Daten: Deutsche Bahn (CC BY 4.0), via piebro/deutsche-bahn-data".
- 파업·사고 등 돌발 상황은 예측 불가 → UI에 "과거 패턴 기반 예보" 문구 고정.
- API 키 등 비밀값은 `.env`, 커밋 금지.
- 확률은 항상 표본 수와 함께 저장 (UI에서 "n=124회 기준" 툴팁).

## 10. 오픈 질문 (작업 중 확인)
- 코리도어에서 실제 운행되는 S-Bahn 노선 (S3/S4 중 Darmstadt까지 가는 비중)
- 공휴일 처리 (Hessen 공휴일 목록: `holidays` 패키지)
- 사이트 이름 최종안 (Bahn-Wetter / 지연예보 / Zugwetter)
- 공유 카드 생성 방식 (Playwright vs satori)
