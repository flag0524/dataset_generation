# status.md — 진행 현황

<!-- 마일스톤별 실시간 진행 상태. 단계 완료 시마다 갱신. 근거: plan.md -->

| 항목 | 내용 |
| --- | --- |
| 최종 갱신 | 2026-06-22 |
| 현재 단계 | M9 완료 (전체 목표 달성) |

---

## 마일스톤 상태

| ID | 마일스톤 | 상태 | 비고 |
| --- | --- | --- | --- |
| M0 | 의사결정 & 환경 | ✅ 완료 | Python·Ollama·웹UI·자체검증 확정 (context-notes.md) |
| M1 | 프로젝트 스캐폴드 | ✅ 완료 | src/, web/, tests/, requirements.txt |
| M2 | 문서 로딩·분석·분류 | ✅ 완료 | loaders.py, pipeline.analyze/route |
| M3 | 지식·규칙 추출 | ✅ 완료 | pipeline.extract_knowledge |
| M4 | LLM 데이터셋 생성 | ✅ 완료 | generate_datasets + synthetic 증강 |
| M5 | Unsloth 포맷 변환 | ✅ 완료 | to_unsloth_formats (raw/alpaca/sharegpt/chatml) |
| M6 | CSV/JSON Export | ✅ 완료 | export.py |
| M7 | 검증 루프 | ✅ 완료 | validate.py (Validator+Judge+크기/구조) |
| M8 | 버전·리포트 | ✅ 완료 | metadata + dataset_report.md |
| M9 | End-to-End 통합 | ✅ 완료 | pytest 9/9 통과, 샘플 100행 PASS(점수 99) |

범례: ✅ 완료 · 🟡 진행중 · ⬜ 대기 · ❌ 실패/블록

## 검증 결과 (tests.md 매트릭스)
- `python -m pytest tests/ -q` → **12 passed**.
- 샘플(`samples/sample_admin.txt`): 도메인=공공행정, 전문가=지방행정 전문가, 100행, 품질점수 99, status=PASS.
- 산출물 8종 생성: csv/json/metadata/report + unsloth_{raw,alpaca,sharegpt,chatml}.jsonl.

## 현재 블로커
- 없음. (선택 항목인 HWP 완전 지원·OCR은 best-effort로 한계 명시됨.)

## 변경 로그
- 2026-06-22: 문서체계 생성 → M0 결정 확정 → M1~M9 구현 및 검증 완료. pytest green.
- 2026-06-23: 원본 qa 중복 시 검증 dedup 후 행 수가 min_rows 아래로 떨어져 FAIL되던 결함 수정. 검증 후 재증강 루프(synthetic.dedupe + 충돌 회피 augment) 추가, 회귀 테스트 1건 추가. pytest 12 passed.
