# Phase 6 — 노선 확장 요약

Frankfurt Hbf ↔ **Darmstadt** 외에 하루 운행이 많은 4개 노선을 추가: **공항 · Wiesbaden · Mainz · Hanau**.

## 노선 선정 (2026-07~09, Frankfurt Hbf에서 하루 운행 수)
Hanau 153 · 공항(지역역) 112 · Wiesbaden 98 · Mainz 73 · Darmstadt 73. 시내 S-Bahn 역(Offenbach 등)은 거리가 짧아 제외.
역 이름/EVA는 데이터 검색으로 확정 (`config/station_search.yaml` → `config/stations.yaml`).
공항은 지역역(08070004)과 장거리역(08070003)을 한 역으로 묶음.

## 결과 (11개월, 노선 양방향)
| 노선 | 하루 운행 | 6분↑ 지연 | 노선 수 |
|---|---|---|---|
| Darmstadt | 172 | 26–27% | 5 |
| 공항 | 324 | 29–33% | 6–7 |
| Wiesbaden | 239 | 33% | 5 |
| Mainz | 148 | 41–45% | 8 |
| Hanau | 314 | 34–37% | 9–10 |

## 백테스트 (`reports/backtest.md`, 홀드아웃 2026-06~09)
- 노선 도착 지연: 모델 Brier 0.2003 vs 노선 평균 0.2129 → **+5.9%**, 방향 평균 대비 +11.1%.
- **10개 방향 모두 베이스라인보다 나음** (+2.4% wi_ffm ~ +8.8% ffm_mz). 품질 게이트(`--strict`) 통과.
- 출발 지연 조건부 예보 +43.4% (`reports/conditional_backtest.md`).

## 바뀐 것
- pipeline: `events.load_trips`가 모든 노선 처리, 방향 키 `ffm_<code>` / `<code>_ffm`.
  export/conditional/profiles/ranking/live 모두 노선 일반화. 한 S8 운행이 여러 노선에 걸치는 경우 중복 제거.
- live.py: 노선 끝 역 전부 조회(회당 ~40요청), 요청 간 1.1초 간격으로 무료 요금제 한도 안.
- site: 노선 칩 + 방향 토글(홈·출퇴근), 노선별 시간표(Hanau처럼 넓으면 가로 스크롤, 시간 열 고정),
  공유 카드에 "오늘의 노선 운세" 줄, 도감은 전체 노선의 상위 12개 열차.
- 테스트: 모든 노선 방향이 실시간 결과에 포함되는지 확인 추가 (9개 통과).

## 배포 시 참고
`stations.yaml`이 바뀌어 Actions의 slim 캐시가 새로 만들어짐 → 다음 데이터 갱신은 11개월치를 다시 받아 20분 정도 걸림.
