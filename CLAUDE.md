# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 상태

8단계 파이프라인이 구현되어 동작한다(end-to-end pytest 통과). 스택은 Python + FastAPI 웹 UI + 로컬 Ollama(미가용 시 mock 폴백) + 자체 검증 루프다.

설계·진행 문서는 `docs/`에 있다.
- `docs/PRD.md`, `docs/TRD.md` — 제품/기술 요구사항 (단일 진실 공급원).
- `docs/goal.md`, `docs/plan.md`, `docs/status.md`, `docs/tests.md` — 목표·계획·진행·검증 매트릭스.
- `docs/context-notes.md` — M0 의사결정 기록(스택 선택 근거).
- `docs/solution_goal.md`, `docs/solution_plan.md`, `docs/solution_status.md`, `docs/solution_tests.md`, `docs/솔루션_구축_기획서.md` — 솔루션 레이어(공공부문 MVP·UI 확장) 목표·계획·진행·검증.
- `docs/domain_dataset_generator_prompt.md`, `docs/Unsloth_데이터셋_생성_및_검증_가이드.md` — 원천 명세.

코드 변경 전 `docs/status.md`로 현재 단계를, 스키마 변경 시 `docs/TRD.md §4`를 먼저 확인하라.

## 명령어

```bash
pip install -r requirements.txt
python -m pytest tests/ -q                                         # 검증 매트릭스(tests.md)
python -m pytest tests/test_pipeline.py::test_t6_validation -q     # 단일 테스트
python -c "from src.runner import run; run('samples/sample_admin.txt')"  # 파이프라인 1회
uvicorn web.app:app --reload                                       # 웹 UI :8000
```

런타임 동작은 환경 변수로 제어한다(`src/config.py`). 주요 값: `USE_MOCK_LLM`(기본 auto, `false`로 두면 실제 Ollama 강제), `OLLAMA_HOST`/`OLLAMA_MODEL`, `LLM_CONCURRENCY`(STEP4 동시 호출), `OUTPUT_DIR`, 검증 게이트 임계값(`MIN_ROWS` 등 — env로 조정 가능, 기본값은 TRD §5와 동일).

## 코드 구조

- `src/runner.py` — 8단계 오케스트레이션 진입점. 새 단계는 여기서 연결한다.
- `src/pipeline.py` — STEP1~4.5 (분석/라우팅/추출/생성/Unsloth 변환). 도메인 라우팅·분류 테이블 포함.
- `src/validate.py` — STEP7 검증 루프(Validator·LLM Judge·크기/구조 게이트).
- `src/export.py` — CSV/JSON/Unsloth jsonl/리포트/메타데이터 직렬화.
- `src/loaders.py` — 포맷별 문서 로더. `src/schemas.py` — 단계 간 계약 검증. `src/llm.py` — Ollama+mock.
- `src/config.py` — 전역 설정·환경 변수 로딩(`Config` 데이터클래스). 게이트 임계값·LLM 설정의 단일 진입점.
- `web/app.py` — FastAPI. 라우트: `/`(랜딩), `/generate`(업로드 UI), `POST /api/generate`, `GET /api/history`, `GET /api/download/{name}`. 정적 페이지는 `web/static/`(landing.html / index.html / dashboard.html). 산출물은 도메인명 프리픽스 파일명으로 다운로드된다.

## 무엇을 만드는가

**도메인 특화 데이터셋 생성 AI 시스템**. 업무 문서를 입력받아 LLM/RAG/AI Agent 학습용 데이터셋(CSV/JSON)을 생성한다. 핵심 원칙은 단순 문서 변환이 아니라 "문서 이해 → 업무 지식 구조화 → AI 학습 데이터 변환"이다.

지원 입력 포맷: PDF, DOCX, XLSX, HWP, PPT, TXT, Markdown, OCR 이미지.

## 처리 파이프라인 (8단계)

명세에 정의된 순차 파이프라인이며, 각 단계가 다음 단계의 입력을 만든다.

1. **문서 분석** — 제목/목적/분야/용어/프로세스/규칙/FAQ 추출, `{document_name, domain, purpose, keywords}` 메타데이터 생성.
2. **도메인 전문가 Agent 선택** — 문서 유형에 따라 전문가 역할 자동 분기 (공공행정 → 지방행정 전문가, 법률 → 법률 분석 전문가, 금융 → 금융 업무 전문가 등).
3. **Knowledge Extraction** — 업무 정의/목적/절차/조직/입출력/규칙 추출. 규칙은 `{rule_id, condition, action, exception}` 구조.
4. **LLM Dataset 생성** — 세 가지 형태를 동시에 생성: Instruction(`instruction/input/output`), Q&A(`question/answer/source`), RAG(`id/title/content/metadata.keyword`).
5. **CSV 생성** — `domain_dataset.csv`. 컬럼: id, domain, category, question, answer, instruction, input, output, source_document, keyword, created_date.
6. **JSON 생성** — `domain_dataset.json`. 레코드별 `id/domain/category/instruction/input/output/metadata{source,keyword}`.
7. **품질 검증** — 원문 근거 확인, 중복 제거, Q&A 품질, 학습 적합성. 결과 `{quality_score, status}`.
8. **버전 관리** — `{version, created_by, record_count}` 데이터셋 메타데이터.

최종 산출물 3종: `domain_dataset.csv`, `domain_dataset.json`, `dataset_report.md`.

확장 대상: RAG 백엔드(ChromaDB/FAISS/Milvus/Pinecone), Fine-tuning(OpenAI/LLaMA/Mistral).

## 구현 시 유의점

- 파이프라인 단계 간 데이터 계약(위 JSON 스키마, TRD §4)을 그대로 지켜라. 컬럼/필드명을 임의로 바꾸면 `tests/`가 깨진다.
- 코드를 만지면 마무리 전 `python -m pytest tests/`를 돌리고 `docs/status.md`를 갱신하라.
- LLM 호출은 `src/llm.py`를 거친다. Ollama 미설치 환경에서도 mock으로 파이프라인이 끝까지 돌아야 한다(테스트 가능성 유지).
