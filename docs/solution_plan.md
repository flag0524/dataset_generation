# solution_plan.md — 구축 계획 (마일스톤 · 작업 분해)

<!-- 근거: solution_goal.md, docs/솔루션_구축_기획서.md §10 로드맵. 무엇을 어떤 순서로 할지. 진행 상태는 solution_status.md, 검증은 solution_tests.md. -->

| 항목 | 내용 |
| --- | --- |
| 문서 버전 | 1.0 |
| 작성일 | 2026-06-24 |

---

## 1. 전체 로드맵 (기획서 §10)

| 단계 | 본 사이클 | 비고 |
| --- | --- | --- |
| S1 분석·설계 | ✅ 본 사이클 | 문서체계·검증구조 수립 |
| S2 MVP 구축 | 🟡 본 사이클(부분) | 도메인명 산출물·진행률·게이트 설정화·HWP/OCR |
| S3 검증 고도화 | ⬜ 차기 | 합성 증강 밸런싱·리포트·버전관리 강화 |
| S4 보안·이행 | ⬜ 차기 | 망분리 패키징·인증·감사 |
| S5 시범 운영 | ⬜ 차기 | 공공행정 파일럿·KPI 측정 |

## 2. 본 사이클 작업 분해 (Now/MVP)

각 작업은 검증 가능한 완료 기준을 가진다(검증은 solution_tests.md 매트릭스와 연결).

| ID | 작업 | 완료 기준(verify) | 의존 |
| --- | --- | --- | --- |
| W1 | 문서체계 4종 작성 | solution_goal/plan/status/tests.md 존재·일관 | — |
| W2 | 산출물 파일명 도메인 한글명 접두 | 도메인별 `<도메인>_dataset.csv/json` 생성, 웹 다운로드·대시보드·테스트 일치 | W1 |
| W3 | 검증 게이트 임계값 설정화 | `min_rows`·`quality_pass_score`를 env로 조정 가능, 기본값 동일 | W1 |
| W4 | 진행률 이벤트 콜백 | `run(..., on_progress=cb)`가 단계별 이벤트 전달, 미지정 시 무동작 | W1 |
| W5 | HWP/OCR 로더 보강 | 결정된 파서로 추출 또는 명확한 폴백 메시지 | 파서 결정 |
| W6 | 회귀 검증·문서 갱신 | pytest 전부 통과, status 갱신, 커밋 | W2~W5 |

## 3. 단계별 실행 순서

```
1. W1 문서체계 → verify: 4종 파일 생성
2. W2 도메인명 산출물 → verify: 도메인 접두 파일 + 테스트 통과
3. W3 게이트 설정화 → verify: env 오버라이드 동작 + 기본값 회귀
4. W4 진행률 콜백 → verify: 콜백 호출 단위 테스트
5. W5 HWP/OCR → verify: 샘플 추출 또는 폴백
6. W6 전체 회귀 → verify: pytest green, status 갱신, 커밋
```

## 4. 의사결정 필요 (기획서 §13, 도달 시 질문)

- W5: HWP 파서 라이브러리(예: `hwp5`/`pyhwp` vs olefile 기반), OCR 엔진(현행 pytesseract 유지 여부).
- 차기: 탑재 로컬 LLM 모델, 저장·버전 관리 방식(FS vs DB), 인증 연계(SSO 종류).

## 5. 스키마 불변 원칙

TRD §4 필드·컬럼명은 고정이다. 파일명만 도메인 접두로 바꾸며, CSV 컬럼 구성(id, domain, category, question, answer, instruction, input, output, source_document, keyword, created_date)은 변경하지 않는다.