# plan.md — 구현 계획

<!-- goal.md를 단계별 실행 계획으로 분해. 각 단계는 verify 기준을 가진다. 근거: goal.md, TRD.md -->

| 항목 | 내용 |
| --- | --- |
| 버전 | 1.0 |
| 근거 | `docs/goal.md`, `docs/TRD.md`, `docs/PRD.md` |

---

## 마일스톤

### M0. 의사결정 & 환경 (선행 필수)
사용자 확정이 필요한 항목. 확정 전 코드 작성 불가.
- 구현 스택, LLM 백엔드, 파서, 검증 루프 방식, 인터페이스 결정.
- verify: 결정 사항이 `context-notes.md`에 기록됨.

### M1. 프로젝트 스캐폴드
- 디렉터리 구조, 의존성 매니페스트, 설정 로더, 샘플 입력 문서 1건.
- verify: 빈 파이프라인이 import·실행되고 "no-op" 통과.

### M2. STEP1~2 — 문서 로딩·분석·도메인 분류
- Document Loader(우선 TXT/MD/PDF), Analyzer, Domain Classifier, Expert Router.
- verify: 샘플 문서 → 메타데이터 JSON 스키마 일치 (TRD §4.1).

### M3. STEP3 — 지식·규칙 추출
- Knowledge Extractor, 규칙 스키마 출력.
- verify: 규칙 JSON 스키마 일치 (TRD §4.2).

### M4. STEP4 — LLM 데이터셋 생성
- Instruction / Q&A / RAG 생성.
- verify: 3종 스키마 일치 (TRD §4.3).

### M5. STEP4.5 — Unsloth 포맷 변환
- Format Converter, chat template 적용, ShareGPT 표준화.
- verify: 4종 포맷 키 일치, 역할 태깅 교대 정확 (TRD §4.8).

### M6. STEP5~6 — CSV/JSON Export
- Exporter, 컬럼·구조 고정.
- verify: csv 컬럼 순서·json 구조 일치 (TRD §4.4/4.5).

### M7. STEP7 — 검증 루프
- Validator, LLM Judge, 크기·구조 점검, Validate→Preview→Refine→Run.
- verify: 무효 행 제외, 품질 점수 산출, 100행/포맷 일관성 게이트.

### M8. STEP8 + 리포트
- Version Manager, Report Builder.
- verify: dataset metadata + `dataset_report.md` 생성.

### M9. End-to-End 통합
- 전체 파이프라인 1회 실행.
- verify: goal.md AC-01~07 전부 통과, tests.md green.

## 실행 순서 원칙
- M0 미완료 시 M1 이후 진행 금지.
- 각 마일스톤 완료 시 `status.md` 갱신 + `tests.md` 해당 항목 실행.
- 스키마 변경 금지 — 계약 위반은 즉시 실패 처리.
