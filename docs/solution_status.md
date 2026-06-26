# solution_status.md — 진행 현황

<!-- 근거: solution_plan.md. 작업 완료 시마다 갱신. -->

| 항목 | 내용 |
| --- | --- |
| 최종 갱신 | 2026-06-24 |
| 현재 단계 | S1 완료, S2(MVP) 본 사이클 완료 |

---

## 작업 상태 (solution_plan.md W1~W6)

| ID | 작업 | 상태 | 비고 |
| --- | --- | --- | --- |
| W1 | 문서체계 4종 | ✅ 완료 | solution_goal/plan/status/tests 작성 |
| W2 | 산출물 도메인명 접두 | ✅ 완료 | runner artifacts 맵 + export prefix + web/index dl() + 테스트 |
| W3 | 게이트 임계값 설정화 | ✅ 완료 | MIN_ROWS/QUALITY_PASS_SCORE/RECOMMENDED_ROWS env |
| W4 | 진행률 이벤트 콜백 | ✅ 완료 | run(on_progress=cb), 8단계 이벤트 |
| W5 | HWP/OCR 로더 보강 | ✅ 완료 | 경량 유지(olefile PrvText) + 명확한 폴백 메시지 |
| W6 | 회귀·문서 갱신 | ✅ 완료 | pytest 16 passed, status 갱신, 커밋 |

범례: ✅ 완료 · 🟡 진행중 · ⬜ 대기 · ❌ 실패/블록

## 의사결정 기록

- 문서체계: 기존 goal/plan/status/tests는 유지하고 solution_* 4종 별도 생성.
- 실행 범위: 문서 + Now/MVP 코드 (보안·SSO·망분리 패키징은 차기).
- 산출물 파일명: 도메인 한글명 접두(예: 공공행정_dataset.csv).
- HWP 파서: 경량 유지(olefile PrvText) + 폴백 강화. pyhwp/hwp5는 차기 검토.

## 현재 블로커

- 없음.

## 차기(별도 사이클) 후보

- S3: 합성 증강 다양성·밸런싱, 리포트·버전 관리 강화.
- S4: 보안·인증(JWT/SSO), PII 비식별, 감사 로그, 망분리 오프라인 패키징.
- §13 미결정: 탑재 로컬 LLM 모델, 저장·버전 관리 방식(FS vs DB), SSO 종류.

## 변경 로그

- 2026-06-24: 솔루션 기획서 분석 → solution_goal/plan/status/tests 문서체계 수립.
- 2026-06-24: Now/MVP 구현 — 산출물 도메인명 접두(W2), 게이트 임계값 env 설정화(W3), 진행률 콜백(W4), HWP/OCR 로더 폴백 강화(W5). 신규 테스트 S-T1/S-T4/S-T5/S-T6 추가, pytest 16 passed.