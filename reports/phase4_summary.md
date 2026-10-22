# Phase 4 — 자동화 요약

## 워크플로
| 파일 | 언제 | 하는 일 |
|---|---|---|
| `.github/workflows/refresh-data.yml` | 매달 3일 06:23 UTC, 수동 실행 | 새 달 다운로드 → slim → 백테스트(품질 게이트) → 확률 테이블 → JSON → main에 커밋 → 배포 호출 |
| `.github/workflows/deploy.yml` | main 푸시, 매일 03:47 UTC, 수동, refresh 후 호출 | 사이트 빌드 → 오늘의 공유 카드 생성 → GitHub Pages 배포 (PR은 빌드·카드 생성만 검증) |

- **매달 갱신인 이유**: 업스트림 가공 데이터가 매달 2일에 한 달 치씩 올라옴. 주 1회 돌려도 숫자는 안 바뀜.
- **품질 게이트**: `backtest.py --strict` — 지연 예보가 노선 평균 베이스라인(b)보다 못하면 실패하고 배포 안 함 (HANDOFF §5.4).
- **백테스트 폴드가 데이터를 따라 이동**: 홀드아웃 = 최근 4개월, 튜닝 = 그 앞 4개월.
- **캐시**: slim parquet(월 ~3 MB)만 Actions 캐시에 보관. 새 달만 받고 원본(월 ~350 MB)은 slim 후 삭제
  (`download.py --skip-slimmed`, `slim.py --delete-source`). 업스트림이 과거 달을 재처리하면 수동 실행 시 `rebuild` 체크.
- **공유 카드**: 매일 `cards/YYYY-MM-DD.png`와 `cards/latest.png`로 배포. 러너에 Noto CJK·컬러 이모지 폰트 설치.
  소개 페이지에 링크 추가.

## 로컬에서 확인한 것
- 워크플로 YAML 파싱, `download.py --skip-slimmed`(이미 있는 11개월 모두 건너뜀), `py_compile`,
  카드 생성 단계(상대 경로 `--out` 버그 발견·수정), `backtest.py --strict` 통과(폴드 동일, 수치 동일).
- GitHub Actions 위에서의 실제 실행은 PR에서 처음 확인됨.

## 저장소 설정 (사람이 해야 함)
1. Settings → Pages → Source: **GitHub Actions**
2. Settings → General → Default branch: **main** (스케줄 실행은 기본 브랜치에서만 동작)
