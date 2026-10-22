# Phase 5 — 실시간 반영 (API 키 제외) 요약

## 구조
API 키를 정적 사이트에 넣을 수 없으므로:
`live.yml` (15분마다, 키는 GitHub Secrets) → `pipeline/live.py` → `live.json`을 `live-data` 브랜치에 강제 푸시
→ 사이트가 `raw.githubusercontent.com`에서 읽음. Pages 재배포 없음. 키가 없으면 워크플로가 스스로 건너뜀(초록 유지).

## 1. 출발 지연 조건부 예보 (`pipeline/conditional.py`) — 키 없이도 동작
"출발역에서 이미 X분 늦은 열차가 목적지에 6분 이상 늦게 도착할 확률"을 과거 기록으로 계산.
방향 × 노선 × 출발 지연 구간(≤1, 2–3, 4–5, 6–9, 10–14, 15–29, 30+분), 노선 전체 쪽으로 축소.

홀드아웃 4개월 백테스트 (`reports/conditional_backtest.md`):
- Brier 0.1884 (시간대 예보) → **0.1115**, **+40.8%**. 모든 구간에서 캘리브레이션 양호.
- 재미있는 사실: 출발 4–5분 지연이면 도착 지연 확률 약 56%, **6분 이상 늦게 출발하면 91–100%** — 따라잡는 일은 거의 없음.
- ⚠️ 과거 기록의 "출발 지연"은 최종값, 실시간 값은 출발 전 예측치라 실제 개선 폭은 이보다 작을 것.

사이트: 출퇴근 표의 칸을 누르면 상세 시트에 "출발이 늦으면?" 표 (지금도 볼 수 있음).

## 2. 실시간 스냅샷 (`pipeline/live.py`)
- Frankfurt Hbf(EVA 2개)·Darmstadt Hbf의 시간별 plan(현재 −1 ~ +2시간) + fchg(변경) → 15개 요청/회.
- **허브 실황**: 지금 ±30분 Frankfurt Hbf 열차 중 6분↑ 지연·취소 비율.
- **코리도어**: 15분 전 ~ 90분 후 출발 열차, 현재 지연, 취소, 조건부 도착 지연 확률.
- 코리도어 판정은 과거 데이터와 같은 규칙(같은 운행 ID가 FFM·DA 둘 다 등장).
- 키 없음 → 아무것도 쓰지 않고 정상 종료. `--fixtures`로 저장된 응답 재생.

## 3. 사이트
- 홈 "지금" 카드에 **실황** 줄 (예: "실황 20:36 · 13% · 예보보다 맑아요").
- 출퇴근에 **🔴 곧 출발** 목록 (정시 / +N분 / 취소, 도착 지연 확률).
- 실시간 데이터가 없음 / 30분 넘게 지남 / fixture 재생본이면 숨김 → 지금 배포해도 실시간 영역은 안 보임.
- 소개 페이지에 실시간 반영 설명 추가.

## 검증
- **실제 API 응답으로 테스트**: piebro raw_data에서 2026-09-09 20:36(베를린) 스냅샷을 잘라 `tests/fixtures/timetables/` (140 KB).
  같은 저녁의 가공 데이터와 대조 → 코리도어 운행 15개 일치, 취소(20:34 RE60) 일치, 실시간 지연은 최종 지연의 이른 추정치.
- `pytest` 8개 통과 (파싱, 변경 반영, 취소, 정렬, 키 없음 처리, CLI). 배포 워크플로 PR 검사에 추가.
- Playwright: 실시간 있음/없음 두 경우, 라이트/다크, 에러 0, 가로 스크롤 없음.

## 키 받은 뒤 할 일
1. DB API Marketplace에서 Timetables API 구독(무료) → Client ID / API Key.
2. GitHub 저장소 Settings → Secrets and variables → Actions에 `DB_CLIENT_ID`, `DB_API_KEY` 추가.
3. Actions → "Live snapshot" → Run workflow로 첫 실행 확인. 로컬에서는 `.env`에 넣고 `uv run python pipeline/live.py --out live/live.json`.
