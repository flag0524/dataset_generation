# tests.md — 검증 구조

<!-- goal.md 성공 기준을 실행 가능한 검증 항목으로 분해. 각 마일스톤 완료 시 해당 항목 실행. -->

| 항목 | 내용 |
| --- | --- |
| 버전 | 1.0 |
| 근거 | `docs/goal.md`(AC), `docs/TRD.md`(스키마) |

---

## 검증 원칙
- 각 항목은 PASS/FAIL이 명확해야 한다(주관 평가 금지).
- 스키마 검증은 TRD §4의 고정 필드명·컬럼 순서를 기준으로 한다.
- 마일스톤 완료 = 대응 테스트 그룹 전부 PASS.

## 테스트 매트릭스

`tests/test_pipeline.py`로 자동화. 결과: **9 passed** (2026-06-22).

### T1. 문서 분석 (M2)
- [x] T1-1 지원 포맷(TXT/MD/PDF) 로딩 성공
- [x] T1-2 메타데이터 JSON에 `document_name/domain/purpose/keywords` 존재 (AC-03) → `test_t1_metadata_schema`
- [x] T1-3 도메인 분류 결과가 라우팅 테이블 키와 매칭 → `test_t1_domain_routing`

### T2. 지식·규칙 추출 (M3)
- [x] T2-1 규칙 객체에 `rule_id/condition/action/exception` 존재 → `test_t2_rule_schema`
- [x] T2-2 지식 항목(정의·절차·조직) 추출

### T3. LLM 데이터셋 (M4)
- [x] T3-1 Instruction 키 `instruction/input/output` → `test_t3_dataset_schemas`
- [x] T3-2 Q&A 키 `question/answer/source`
- [x] T3-3 RAG 키 `id/title/content/metadata.keyword`

### T4. Unsloth 포맷 (M5)
- [x] T4-1 Raw `text` / Alpaca `Instruction/Input/Output` 키 일치 → `test_t4_formats`
- [x] T4-2 ShareGPT `conversations[].from/value`, human↔gpt 교대 (AC-04)
- [x] T4-3 ChatML `messages[].role/content`, user↔assistant 교대 (AC-04)
- [~] T4-4 채팅 템플릿 적용 후 토크나이즈 — 구조 보장(키 규약). 실제 토크나이즈는 Unsloth 환경에서 검증(범위 외)

### T5. Export (M6)
- [x] T5-1 CSV 컬럼 순서 일치 (id…created_date) → `test_t5_csv_columns`
- [x] T5-2 JSON 레코드 구조 일치 (AC-02) → `test_t5_json_exists`

### T6. 검증 루프 (M7)
- [x] T6-1 Validator가 무효 행 제외 (AC-07)
- [x] T6-2 LLM Judge 점수 산출·저품질 필터링 (AC-07)
- [x] T6-3 데이터셋 ≥100행 (AC-05) → `test_t6_validation`
- [x] T6-4 품질 점수 ≥90 & status PASS (AC-06)
- [x] T6-5 포맷 일관성·역할 태깅 100% (AC-04)

### T7. 산출물 & 통합 (M8/M9)
- [x] T7-1 산출물 파일 생성 (AC-02) → `test_t7_artifacts`
- [x] T7-2 dataset metadata `version/created_by/record_count`
- [x] T7-3 `dataset_report.md` 생성
- [x] T7-4 End-to-End 무중단 실행 (AC-01)

## 실행 방법
```
pip install -r requirements.txt
python -m pytest tests/ -q          # 검증 매트릭스 실행
python -c "from src.runner import run; run('samples/sample_admin.txt')"  # 파이프라인 1회 실행
uvicorn web.app:app --reload        # 웹 UI (http://localhost:8000)
```
범례: [x] 통과 · [~] 부분/범위 외 · [ ] 미수행
