# status.md — 진행 현황

<!-- 마일스톤별 실시간 진행 상태. 단계 완료 시마다 갱신. 근거: plan.md -->

| 항목 | 내용 |
| --- | --- |
| 최종 갱신 | 2026-06-25 |
| 현재 단계 | M9 완료 (전체 목표 달성) + 웹 UI·솔루션 레이어 확장 |

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
- 2026-06-23: STEP4 데이터셋 생성을 segment×과제앵글로 개편해 input(원문)과 output(결과물)이 겹치지 않게 함. RAG 패시지는 원문 단위 1건으로 분리(dedupe도 rag 비정렬 처리). OCR 로더의 Tesseract 경로를 환경변수(TESSERACT_CMD/TESSDATA_PREFIX)로 설정 가능하게 함. pytest 12 passed.
- 2026-06-23: 작은/저품질 문서를 min_rows까지 무리하게 부풀려 같은 내용이 반복되던 문제 완화. 합성 행을 원본의 최대 MAX_SYNTHETIC_MULT(5)배까지만 생성하고(부족하면 그 선에서 정지), 증강 변형을 '(변형 N)' 번호 대신 재진술 틀(_VARIANT_STYLES)로 다양화. pytest 12 passed.
- 2026-06-26: ZIP 기반 포맷(DOCX/XLSX/PPTX)에 구형 바이너리(.doc/.xls/.ppt)나 손상 파일을 올리면 `File is not a zip file`(BadZipFile)·`PackageNotFoundError`가 500으로 노출되던 문제 수정. 로더에서 해당 예외를 한국어 ValueError로 변환해 400으로 안내. 회귀 테스트 3건(.docx/.xlsx/.pptx) 추가. 이어서 `_sniff_format`(매직 바이트+OLE 내부 스트림)으로 실제 포맷(구형 Excel .xls/Word .doc/PPT .ppt/HWP/PDF/손상)을 감지해 오류 메시지에 명시 — 새 의존성 없이 기존 olefile 활용. 감지 테스트 1건 추가. pytest 21 passed.
- 2026-06-26: `_sniff_format`을 텍스트 계열까지 확장. 공공·기업 시스템이 보고서를 HTML 표·Excel 2003 XML(SpreadsheetML)·CSV/텍스트로 내보내며 확장자만 .xls/.xlsx로 붙이는 "가짜 엑셀"을 BOM 제거 후 식별하고, 미상이면 첫 바이트 hex를 노출. 안내 문구 중복 제거(_CONVERT_HINT 분리). pytest 21 passed.
- 2026-06-26: 실제 Ollama 사용 시 문서 크기에 비례해 응답이 수 분까지 늘어나던 문제 해결. STEP3~4 LLM 작업에 벽시계 예산(LLM_TIME_BUDGET, 기본 25초)을 도입해, 예산 초과·임박 세그먼트는 휴리스틱으로 즉시 폴백하고 호출 타임아웃도 남은 예산으로 제한. 산출물 행 수·구조는 불변(증강이 min_rows 충족). 시간 예산 회귀 테스트 1건 추가. pytest 17 passed.
- 2026-06-25: 핵심 파이프라인 완료 이후 웹 UI·솔루션 레이어 확장. 데이터셋 히스토리 대시보드(백엔드+UI) 추가, Unsloth 분석 매뉴얼·솔루션 제안서 문서화, 솔루션 문서 시스템 + 공공부문 MVP(도메인명 산출물·게이트·진행률·로더), 도메인명 다운로드 링크 + 다크 네이비/라임 테마 적용.
