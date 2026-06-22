# goal.md — 프로젝트 목표 정의

<!-- 무엇을 달성하면 "끝"인지 정의하는 단일 기준 문서. 근거: PRD.md, TRD.md -->

| 항목 | 내용 |
| --- | --- |
| 버전 | 1.0 |
| 작성일 | 2026-06-22 |
| 근거 | `docs/PRD.md`, `docs/TRD.md` |

---

## 1. 최종 목표 (Definition of Done)

업무 문서를 입력하면 도메인을 분석하고 지식을 추출해, **Unsloth 파인튜닝에 바로 투입 가능한 검증된 학습 데이터셋**(CSV/JSON + Raw/Alpaca/ShareGPT/ChatML)을 생성하는 동작하는 시스템을 완성한다.

"끝"의 조건:
1. 지원 포맷 문서를 입력해 8단계 파이프라인이 끝까지 자동 실행된다.
2. `domain_dataset.csv`, `domain_dataset.json`, Unsloth 학습 포맷, `dataset_report.md`가 생성된다.
3. 검증 루프(Validate→Preview→Refine→Run)가 동작하고 품질 점수·PASS/FAIL이 산출된다.
4. `tests.md`의 모든 검증 항목이 통과한다.

## 2. 성공 기준 (Acceptance Criteria)

PRD §9 KPI와 정렬한다.

| ID | 기준 | 측정 |
| --- | --- | --- |
| AC-01 | 8단계 파이프라인 무중단 실행 | 샘플 문서 1건 end-to-end 성공 |
| AC-02 | 4종 산출물 생성 | 파일 존재 + 스키마 일치 |
| AC-03 | 단계 간 스키마 필드명 불변 | TRD §4 계약 검증 통과 |
| AC-04 | Unsloth 포맷 일관성 | 역할 태깅·템플릿 일치 100% |
| AC-05 | 데이터셋 크기 | 최소 100행 충족 |
| AC-06 | 품질 검증 | 평균 점수 ≥90, PASS |
| AC-07 | 자동 검증 동작 | Validator·LLM Judge로 무효/저품질 행 필터링 |

## 3. 범위 (Scope)

- 포함: 문서 파싱 → 분석 → 지식추출 → 데이터셋 생성 → 포맷 변환 → 검증 → 산출.
- 제외(PRD Non-Goals): 모델 학습 실행, 협업 편집, 단순 문서 변환.

## 4. 진행 원칙

- 의사결정이 필요한 지점(스택, LLM 백엔드, 파서 등)은 **반드시 사용자에게 질문 후** 진행한다.
- 단계 완료 시 `status.md`를 갱신하고, 검증은 `tests.md` 기준으로 수행한다.
- 결정 사항은 `docs/context-notes.md`(필요 시 생성)에 누적 기록한다.
