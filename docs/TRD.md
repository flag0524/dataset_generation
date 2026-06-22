# TRD — 도메인 특화 데이터셋 생성 AI 시스템

<!-- 기술 요구사항 정의서. PRD의 기능을 어떻게 구현할지 정의한다. 무엇/왜는 PRD.md 참조. -->

| 항목 | 내용 |
| --- | --- |
| 문서 버전 | 1.0 |
| 작성일 | 2026-06-22 |
| 상태 | Draft |
| 근거 문서 | `docs/domain_dataset_generator_prompt.md`, `docs/Unsloth_데이터셋_생성_및_검증_가이드.md`, `docs/PRD.md` |

---

## 1. 아키텍처 개요

8단계 순차 파이프라인 구조다. 각 단계는 이전 단계의 출력을 입력으로 받아 변환하며, 단계 간 데이터는 정의된 JSON 스키마로 전달한다.

```
[문서 업로드]
   ↓
STEP1 문서 분석 ──→ document metadata
   ↓
STEP2 도메인 전문가 Agent 라우팅
   ↓
STEP3 Knowledge Extraction ──→ knowledge + rules
   ↓
STEP4 LLM Dataset 생성 ──→ Instruction / Q&A / RAG
   ↓
STEP4.5 Unsloth 포맷 변환 ──→ Raw / Alpaca / ShareGPT / ChatML (+chat template)
   ↓
STEP5 CSV 생성        STEP6 JSON 생성
   ↓
STEP7 품질 검증 (검증 루프: Validate→Preview→Refine→Run)
        · Validator(린트) · LLM Judge(채점) · 크기/구조 점검
   ↓
STEP8 버전 관리 ──→ dataset metadata
   ↓
[산출물: csv / json / unsloth 포맷 / report.md]  ──(선택)──► HF 게시
```

## 2. 컴포넌트 설계

| 컴포넌트 | 책임 | 비고 |
| --- | --- | --- |
| Document Loader | 다중 포맷 파싱 → 평문 텍스트 | 포맷별 어댑터 패턴 |
| Document Analyzer | 메타데이터·구조 분석 | LLM 호출 |
| Domain Classifier | 도메인 분류 | 규칙 + LLM 분류 |
| Expert Agent Router | 도메인별 프롬프트/역할 선택 | 전략 패턴 |
| Knowledge Extractor | 업무 지식·규칙 추출 | LLM 호출 |
| Dataset Generator | Instruction/Q&A/RAG 생성 | LLM 호출 |
| Format Converter | Raw/Alpaca/ShareGPT/ChatML 변환, chat template 적용 | Unsloth 연계 |
| Synthetic Generator | 합성 데이터 생성·다양화·증강 | LLM 호출 |
| Exporter (CSV/JSON/JSONL) | 표준 스키마·학습 포맷으로 직렬화 | |
| Validator | 코드/구조 린트로 무효 행 자동 제외 | Python/SQL/JS |
| LLM Judge | 사용자 정의 기준 행별 채점·필터링 | LLM 호출 |
| Quality Validator | 근거·중복·크기·구조 검사, 점수화 | 검증 루프 오케스트레이션 |
| Report Builder | 리포트 마크다운 생성 | |
| Version Manager | 데이터셋 메타데이터 관리 | |

## 3. 입력 포맷 처리

| 포맷 | 처리 방식(권장 후보) |
| --- | --- |
| PDF | 텍스트 추출 라이브러리 |
| DOCX / PPT / XLSX | Office 파서 |
| HWP | 한글 전용 파서 (선택 필요) |
| TXT / Markdown | 직접 로드 |
| OCR 이미지 | OCR 엔진 → 텍스트 |

구체 라이브러리는 구현 스택 확정 후 결정한다(미해결).

## 4. 데이터 스키마 (단계 간 계약)

필드명·컬럼명은 명세 고정값이며 변경 금지다.

### 4.1 STEP1 — 문서 메타데이터

```json
{
  "document_name": "",
  "domain": "",
  "purpose": "",
  "keywords": []
}
```

### 4.2 STEP3 — 규칙 데이터

```json
{
  "rule_id": "R001",
  "condition": "",
  "action": "",
  "exception": ""
}
```

추출 지식 항목: 업무 정의, 업무 목적, 처리 절차, 담당 조직, 입력 데이터, 처리 규칙, 결과 데이터.

### 4.3 STEP4 — LLM 데이터셋

```json
// Instruction
{ "instruction": "", "input": "", "output": "" }

// Q&A
{ "question": "", "answer": "", "source": "" }

// RAG
{ "id": "", "title": "", "content": "", "metadata": { "keyword": [] } }
```

### 4.4 STEP5 — CSV 스키마

파일명 `domain_dataset.csv`. 컬럼 순서 고정.

```
id, domain, category, question, answer, instruction, input, output, source_document, keyword, created_date
```

### 4.5 STEP6 — JSON 스키마

파일명 `domain_dataset.json`.

```json
[
  {
    "id": "001",
    "domain": "",
    "category": "",
    "instruction": "",
    "input": "",
    "output": "",
    "metadata": { "source": "", "keyword": [] }
  }
]
```

### 4.6 STEP7 — 품질 검증 결과

```json
{ "quality_score": 95, "status": "PASS" }
```

검증 항목: 원문 근거 확인, 중복 제거, 질문/답변 품질, LLM 학습 적합성.

### 4.7 STEP8 — 데이터셋 메타데이터

```json
{ "version": "1.0", "created_by": "AI Dataset Generator", "record_count": 0 }
```

### 4.8 STEP4.5 — Unsloth 학습 포맷

내부 데이터셋(Instruction/Q&A/RAG)을 아래 4종으로 변환한다. 키 이름은 Unsloth/HF 규약 고정값이다.

```json
// Raw Corpus (CPT)
{ "text": "..." }

// Alpaca / Instruct (SFT)
{ "Instruction": "", "Input": "", "Output": "" }

// ShareGPT (다중 턴 SFT) — from: human|gpt 교대
{ "conversations": [ { "from": "human", "value": "" }, { "from": "gpt", "value": "" } ] }

// ChatML (OpenAI/HF 기본) — role: user|assistant 교대
{ "messages": [ { "role": "user", "content": "" }, { "role": "assistant", "content": "" } ] }
```

변환 규칙:
- ShareGPT(`from/value`) 입력은 `standardize_sharegpt()`로 ChatML 표준화 후 처리.
- 다중 컬럼 CSV는 `to_sharegpt`로 병합(`{}` 컬럼 바인딩, `[[ ]]` 선택 항목 자동 제외).
- 채팅 템플릿은 `get_chat_template(tokenizer, chat_template=...)`로 모델별 적용(llama-3.1/qwen2.5/gemma-3 등).
- 단일 턴 → 다중 턴 확장은 `conversation_extension` 활용.

## 5. 검증 루프 (Validate → Preview → Refine → Run)

데이터를 일괄 생성하지 않고 반복 검증 루프로 처리한다.

```
Validate ──► Preview ──► Refine ──► Run(Full Build)
   ▲                          │
   └──────── 반복 ◄───────────┘
```

| 단계 | 처리 |
| --- | --- |
| Validate | 블록 연결·참조·프롬프트·스키마 설정 오류를 실행 전 검출 |
| Preview | 샘플 행만 생성해 즉시 점검(빠른 반복) |
| Refine | 프롬프트·시드·Validator 기준을 다듬어 재시도 |
| Run | 기준 충족 시 전체 빌드 → 영구 데이터셋 아티팩트 저장 |

검증 컴포넌트:
- **Validator** — LLM Code 출력 등을 Python/SQL/JS 린터·구문 검사로 통과시키고 무효 행 자동 제외.
- **LLM Judge** — 사용자 정의 점수 기준으로 행별 채점, 저품질 행 필터링.
- **수동 품질·밸런싱** — 합성 데이터의 관련성·편향 점검, 과적합 방지 위해 영역 균형.

크기·구조 검증 기준:

| 항목 | 기준 |
| --- | --- |
| 최소 분량 | 100행 |
| 권장 분량 | 1,000행 이상 |
| 부족 시 | 합성 데이터 추가 / HF 데이터셋으로 다양화 |
| 구조 | 토크나이즈 가능, 역할 태깅 정확, 채팅 템플릿 일치, 포맷 전체 일관 |

## 6. 도메인 전문가 Agent 라우팅

문서 유형에 따라 전문가 역할을 자동 선택한다. 라우팅 규칙은 확장 가능한 매핑 테이블로 구현한다.

| 문서 유형 | 전문가 역할 |
| --- | --- |
| 공공행정 문서 | 지방행정 전문가 |
| 법률 문서 | 법률 분석 전문가 |
| 금융 문서 | 금융 업무 전문가 |
| (확장) | 신규 도메인 추가 시 매핑만 등록 |

## 7. 확장 연동

- **RAG 벡터 스토어**: ChromaDB, FAISS, Milvus, Pinecone — RAG 데이터셋을 각 백엔드 포맷으로 export하는 어댑터.
- **Unsloth 파인튜닝**: 변환된 학습 포맷을 Unsloth로 직접 학습. (선택) Data Recipes(NeMo Data Designer) 노코드 워크플로우 연계.
- **Fine-tuning 포맷**: OpenAI Fine-tuning(JSONL), LLaMA, Mistral 학습 포맷 변환기.
- **Hugging Face**: 완성 데이터셋 게시.
- **추론 모델 대응**: 추론 모델(예: DeepSeek-R1-Distill) 학습 시 답변에 chain-of-thought 포함, 비추론 모델에 추론 학습 시 GRPO(강화학습) 경로 별도.

## 8. 비기능 요구사항

| 항목 | 요구사항 |
| --- | --- |
| 품질 | 품질 점수 90점 이상 목표, PASS/FAIL 상태 명시 |
| 일관성 | 단계 간 스키마 필드명 불변 |
| 확장성 | 도메인·포맷·RAG 백엔드를 어댑터/매핑 추가로 확장 |
| 추적성 | 모든 데이터에 원문 출처(source_document) 보존 |
| 재현성 | 데이터셋 버전·생성 이력 관리 |
| 품질 게이트 | 학습 포맷 일관성·역할 태깅 검증 100% 통과 전 Run 차단 |

## 9. 기술 결정 대기 항목 (Decisions Needed)

본 시스템은 LLM 호출이 핵심이므로, 코드 작성 전 아래를 확정해야 한다.

- 구현 언어/프레임워크 (Unsloth 연계상 Python 유력).
- LLM 백엔드 (Claude API 등 클라우드 vs 로컬 모델). 합성 데이터 생성 모델 포함.
- 문서 파서 라이브러리 (특히 HWP, OCR).
- 검증 루프 구현 방식 (자체 구현 vs Unsloth Data Recipes/NeMo Data Designer 위임).
- 채팅 템플릿 대상 모델 기본값 (llama-3.1 / qwen3.5 / gemma-3 / gemma-4 등).
- 실행 인터페이스 (CLI / 배치 / 웹 API).
- 데이터셋 저장·버전 관리 방식 (파일 시스템 / DB / HF).
