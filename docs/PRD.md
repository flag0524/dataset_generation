# PRD — 도메인 특화 데이터셋 생성 AI 시스템

<!-- 제품 요구사항 정의서. 무엇을, 누구를 위해, 왜 만드는지를 정의한다. 기술 구현은 TRD.md 참조. -->

| 항목 | 내용 |
| --- | --- |
| 문서 버전 | 1.0 |
| 작성일 | 2026-06-22 |
| 상태 | Draft |
| 근거 문서 | `docs/domain_dataset_generator_prompt.md`, `docs/Unsloth_데이터셋_생성_및_검증_가이드.md` |

---

## 1. 개요

업무 문서를 업로드하면 해당 도메인의 전문 지식을 자동으로 구조화하고, LLM·RAG·AI Agent 학습에 바로 활용 가능한 데이터셋(CSV/JSON)을 생성하는 AI 시스템이다.

핵심 차별점은 단순 문서 변환기가 아니라는 점이다. 문서 이해 → 업무 지식 구조화 → AI 학습 데이터 변환의 3단계 지능형 처리를 수행한다.

## 2. 문제 정의

- 기업·기관이 보유한 업무 문서(규정, 매뉴얼, FAQ 등)는 비정형 상태라 LLM 학습이나 RAG에 바로 쓸 수 없다.
- 학습용 데이터셋을 수작업으로 만들면 시간이 많이 들고 도메인 전문성이 누락되기 쉽다.
- 포맷(PDF, HWP, XLSX 등)이 제각각이라 일관된 전처리가 어렵다.

## 3. 목표 (Goals)

- 업로드된 문서에서 도메인을 자동 분류하고 전문 지식을 추출한다.
- LLM 학습용 3종 데이터셋(Instruction, Q&A, RAG)을 자동 생성한다.
- 생성 데이터를 **Unsloth 파인튜닝에 바로 투입 가능한 학습 포맷**(Alpaca/ShareGPT/ChatML, Raw text)으로 변환한다.
- 표준 산출물(CSV, JSON, 리포트)을 일관된 스키마로 제공한다.
- **검증 우선 루프(Validate → Preview → Refine → Run)** 로 생성 데이터의 품질을 자동·반복 검증하고 점수화한다.
- 데이터셋 크기·구조 기준(최소 100행, 권장 1,000행 이상, 포맷 일관성)을 충족하는지 점검한다.

### 목표가 아닌 것 (Non-Goals)

- 문서를 단순 텍스트로 변환만 하는 기능.
- 실시간 협업 편집이나 문서 작성 도구.
- 모델 학습(파인튜닝) 실행 자체. 본 시스템은 Unsloth로 학습 가능한 데이터셋 생성·검증까지만 책임지며, 학습 실행은 Unsloth/외부 도구에 위임한다.

## 4. 대상 사용자

| 페르소나 | 니즈 |
| --- | --- |
| AI 데이터 엔지니어 | 도메인 문서를 학습 데이터셋으로 빠르게 변환 |
| 도메인 실무자(공공/법률/금융) | 자기 업무 지식을 AI가 이해할 형태로 정리 |
| LLM/RAG 시스템 구축자 | 검증된 RAG·Instruction 데이터 확보 |

## 5. 핵심 사용자 시나리오

1. 사용자가 업무 문서(예: 지방행정 규정 PDF)를 업로드한다.
2. 시스템이 문서를 분석해 도메인을 "공공행정"으로 분류하고 메타데이터를 생성한다.
3. 도메인에 맞는 전문가 Agent(지방행정 전문가)가 업무 지식과 규칙을 추출한다.
4. Instruction / Q&A / RAG 데이터셋이 생성된다.
5. 사용자가 CSV·JSON·리포트 산출물을 내려받는다.
6. 품질 점수와 검증 상태(PASS/FAIL)를 확인한다.

## 6. 기능 요구사항

| ID | 기능 | 설명 | 우선순위 |
| --- | --- | --- | --- |
| FR-01 | 다중 포맷 문서 업로드 | PDF, DOCX, XLSX, HWP, PPT, TXT, Markdown, OCR 이미지 지원 | High |
| FR-02 | 문서 분석 | 제목/목적/분야/조직/용어/프로세스/규칙/FAQ 추출 및 메타데이터 생성 | High |
| FR-03 | 도메인 자동 분류 | 문서 유형 기반 도메인 판별 | High |
| FR-04 | 도메인 전문가 Agent 라우팅 | 도메인별 전문가 역할 자동 선택 | High |
| FR-05 | 지식 추출 | 업무 정의/목적/절차/조직/입출력/규칙 구조화 | High |
| FR-06 | LLM 데이터셋 생성 | Instruction, Q&A, RAG 3종 생성 | High |
| FR-07 | CSV 산출 | 표준 컬럼 스키마로 `domain_dataset.csv` 생성 | High |
| FR-08 | JSON 산출 | 표준 구조로 `domain_dataset.json` 생성 | High |
| FR-09 | Unsloth 학습 포맷 변환 | Raw text / Alpaca / ShareGPT / ChatML 포맷으로 export | High |
| FR-10 | 채팅 템플릿 적용 | 모델별 chat template 적용, ShareGPT→ChatML 표준화 | Medium |
| FR-11 | 합성 데이터 생성 | 분량 부족·다양성 부족 시 합성 예시 생성·증강 | Medium |
| FR-12 | 자동 검증(Validator) | 코드/구조 린트로 유효하지 않은 행 자동 제외 | High |
| FR-13 | 품질 채점(LLM Judge) | 사용자 정의 기준으로 행별 점수화·필터링 | High |
| FR-14 | 검증 루프 | Validate → Preview → Refine → Run 반복 워크플로우 | High |
| FR-15 | 크기·구조 검증 | 최소 100행/권장 1,000행, 역할 태깅·포맷 일관성 점검 | High |
| FR-16 | 리포트 생성 | `dataset_report.md` 생성 | Medium |
| FR-17 | 버전 관리 | 데이터셋 메타데이터(version, record_count 등) 관리 | Medium |
| FR-18 | RAG 백엔드 연동 | ChromaDB/FAISS/Milvus/Pinecone로 export | Low |
| FR-19 | HF 게시 | 완성 데이터셋을 Hugging Face 저장소에 게시 | Low |

## 7. 산출물

1. `domain_dataset.csv` — 표 형식 통합 데이터셋.
2. `domain_dataset.json` — 구조화 데이터셋.
3. **Unsloth 학습 포맷 파일** — Raw text / Alpaca / ShareGPT / ChatML 중 선택 export(JSON/JSONL).
4. `dataset_report.md` — 생성·검증 결과 요약 리포트(품질 점수, 행 수, 포맷 일관성 포함).

## 8. Unsloth 연계 (학습 포맷 & 검증)

### 8.1 학습 포맷

본 시스템은 추출한 지식을 다음 4종 포맷으로 변환해 Unsloth 파인튜닝에 바로 투입할 수 있게 한다.

| 포맷 | 용도(학습 방식) |
| --- | --- |
| Raw Corpus (`text`) | 계속 사전학습 (CPT) |
| Instruct / Alpaca (`Instruction/Input/Output`) | 지도 미세조정 (SFT) |
| ShareGPT (`conversations`, `from/value`) | 다중 턴 대화 SFT |
| ChatML (`messages`, `role/content`) | OpenAI/HF 기본 SFT |

### 8.2 검증 루프

데이터를 한 번에 생성하지 않고 **Validate → Preview → Refine → Run** 반복 루프로 검증한다. 자동 검증은 Validator(코드/구조 린트)와 LLM Judge(품질 채점)로, 수동 검증은 품질·밸런싱 점검으로 수행한다. 합성 데이터는 과적합 방지를 위해 다양성·밸런싱을 추가로 점검한다.

## 9. 성공 지표 (KPI)

- 품질 검증 평균 점수 90점 이상, 상태 PASS 비율 95% 이상.
- 문서당 데이터셋 생성 자동화율(수작업 개입 없이 완료) 90% 이상.
- 지원 포맷 8종 전부 정상 파싱.
- 생성 데이터셋 **최소 100행 충족**, 권장 1,000행 이상 달성.
- 학습 포맷 일관성(역할 태깅·템플릿 일치) 검증 통과율 100%.

## 10. 데이터 계약 (요약)

상세 스키마는 `TRD.md` 참조. 파이프라인 단계 간 필드명·컬럼명은 변경 금지다.

- 문서 메타데이터: `document_name`, `domain`, `purpose`, `keywords[]`
- 규칙: `rule_id`, `condition`, `action`, `exception`
- Instruction: `instruction`, `input`, `output`
- Q&A: `question`, `answer`, `source`
- RAG: `id`, `title`, `content`, `metadata.keyword[]`
- Unsloth 학습 포맷: Raw(`text`), Alpaca(`Instruction/Input/Output`), ShareGPT(`conversations[].from/value`), ChatML(`messages[].role/content`)

## 11. 미해결 이슈 (Open Questions)

- 구현 스택(언어/프레임워크) 미정. (Unsloth 연계상 Python 유력)
- 문서 파싱 라이브러리 선택(특히 HWP, OCR) 미정.
- LLM 추론 백엔드(클라우드 API vs 로컬 모델) 미정. 합성 데이터 생성용 모델 포함.
- 채팅 템플릿 대상 모델(llama-3.1 / qwen3.5 / gemma-3, gemma-4 등) 기본값 미정.
- 검증 루프를 자체 구현할지 Unsloth Data Recipes(NeMo Data Designer)에 위임할지 미정.
- UI 제공 여부(CLI 전용 vs 웹 인터페이스) 미정.
