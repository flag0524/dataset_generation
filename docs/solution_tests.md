# solution_tests.md — 검증 매트릭스

<!-- 근거: solution_goal.md DoD, solution_plan.md 작업. 각 작업의 완료를 무엇으로 확인하는지. -->

| 항목 | 내용 |
| --- | --- |
| 문서 버전 | 1.0 |
| 작성일 | 2026-06-24 |
| 실행 | `python -m pytest tests/ -q` |

---

## 1. 검증 매트릭스

| TID | 대상(작업) | 검증 방법 | 통과 기준 |
| --- | --- | --- | --- |
| S-T1 | W2 도메인명 산출물 | 파이프라인 1회 실행 후 산출물 파일명 확인 | `<도메인>_dataset.csv`·`<도메인>_dataset.json` 생성 |
| S-T2 | W2 웹/대시보드 연계 | `/api/download/{name}` 및 다운로드 링크 | 도메인명 파일 다운로드 성공(200) |
| S-T3 | W2 스키마 불변 | CSV 컬럼·JSON 필드 비교 | TRD §4 컬럼/필드 변경 없음 |
| S-T4 | W3 게이트 설정화 | `MIN_ROWS`·`QUALITY_PASS_SCORE` env 오버라이드 | 값 반영, 미설정 시 기본(100/90) |
| S-T5 | W4 진행률 콜백 | `run(on_progress=cb)` 호출 | 콜백이 단계별 1회 이상 호출됨 |
| S-T6 | W5 HWP/OCR 로더 | 샘플 입력 로드 | 텍스트 추출 또는 명확한 폴백 메시지 |
| S-T7 | 회귀(기존 파이프라인) | 기존 `tests/` 전체 | 전부 통과(품질·크기·포맷 게이트 유지) |
| S-T8 | KPI 회귀(샘플) | sample_admin 실행 | 100행·품질 90+·status PASS |

## 2. KPI 게이트 (기획서 §9)

| 지표 | 목표 | 검증 |
| --- | --- | --- |
| 평균 품질 점수 | ≥ 90 | validation.quality_score |
| PASS 비율 | ≥ 95% | history.jsonl 집계 (/api/history) |
| 자동화율 | ≥ 90% | 수작업 개입 없이 완료 비율 |
| 분량 | ≥ 100행 | validation.size_ok |
| 포맷 일관성 | 100% | validation.format_consistent |
| 외부 통신 | 0건 | 외부 호출 코드경로 부재(차기 보안 검토에서 정밀 확인) |

## 3. 회귀 보호 원칙

- 기존 12개 테스트는 항상 green을 유지한다. 파일명 변경(W2)으로 깨지는 테스트는 새 규칙에 맞춰 수정하되, 검증 의미(행 수·품질·포맷)는 보존한다.
- 신규 작업(W2~W5)마다 최소 1개의 회귀/단위 테스트를 추가한다.