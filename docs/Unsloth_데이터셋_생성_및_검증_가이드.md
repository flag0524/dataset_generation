# Unsloth 데이터셋 생성 및 검증 가이드

> 출처: Unsloth 공식 문서 — Datasets Guide, Unsloth Data Recipes (unsloth.ai/docs)
> 작성 기준: 2026년 6월

파인튜닝 결과의 품질은 모델 자체보다 **데이터셋의 품질·구조**에 크게 좌우됩니다. 본 문서는 Unsloth에서 데이터셋을 만드는 전체 과정과, 각 단계에서 데이터를 검증하는 방법을 정리합니다.

---

## 1. 데이터셋이란

LLM 학습용 데이터셋은 **토크나이즈(tokenize)가 가능한 형식**으로 정리된 데이터 모음입니다. 텍스트는 토큰으로 분해되고, 토큰은 임베딩으로 변환되어 모델이 의미와 맥락을 학습합니다. 따라서 데이터는 토크나이저가 읽을 수 있는 일관된 포맷이어야 합니다.

### 데이터 포맷 4종류

| 포맷 | 설명 | 학습 방식 |
|------|------|-----------|
| **Raw Corpus** | 웹사이트·책·기사 등에서 추출한 가공되지 않은 원시 텍스트 | 계속 사전학습 (CPT) |
| **Instruct** | 모델이 수행할 지시문 + 기대 출력 예시 | 지도 미세조정 (SFT) |
| **Conversation** | 사용자와 AI 어시스턴트 간의 다중 턴 대화 | 지도 미세조정 (SFT) |
| **RLHF** | 대화에 대해 스크립트·다른 모델·사람이 응답 순위를 매긴 데이터 | 강화학습 (RL) |

---

## 2. 데이터셋 생성 과정

### 2-1. 사전 정의 (3가지 식별)

데이터를 포맷팅하기 전에 다음 세 가지를 먼저 정합니다.

1. **데이터셋의 목적 (Purpose)**
   - 어떤 데이터와 포맷이 필요한지를 결정합니다.
   - 예) 챗봇 대화(Q&A·고객지원), 구조화 작업(분류·요약·생성), 도메인 특화(의료·금융·기술)

2. **출력 스타일 (Style of output)**
   - 원하는 출력 형태를 정합니다. 예) JSON, HTML, 텍스트, 코드 / 언어(한국어·영어·독일어 등)

3. **데이터 소스 (Data source)**
   - 목적·스타일이 정해지면 데이터의 품질과 분량을 분석합니다.
   - 소스: CSV, PDF, 웹사이트, Hugging Face, Wikipedia(언어 학습에 유용) 또는 합성 데이터.
   - **팁:** ShareGPT 같은 일반화된 HF 데이터셋과 결합하면 모델이 더 똑똑하고 다양해집니다.

### 2-2. 데이터 포맷팅

목적·소스가 정해지면 학습 가능한 형식으로 변환합니다.

**① 계속 사전학습 (Raw text)**
```json
{ "text": "Pasta carbonara is a traditional Roman pasta dish..." }
```

**② Instruction 포맷 (Alpaca 스타일)**
```json
{
  "Instruction": "모델이 수행할 작업",
  "Input": "선택 사항이지만 유용 — 사용자 질의에 해당",
  "Output": "기대 결과(모델 출력)"
}
```

**③ ShareGPT 포맷 (다중 턴 대화)**
- `from` / `value` 키를 사용하며 `human` ↔ `gpt`가 번갈아 등장
```json
{
  "conversations": [
    { "from": "human", "value": "카르보나라 만드는 법 알려줘?" },
    { "from": "gpt", "value": "전통 로마식과 간단 버전 중 어느 쪽이 좋으세요?" }
  ]
}
```

**④ ChatML 포맷 (OpenAI / Hugging Face 기본)**
- `role` / `content` 키를 사용하며 `user` ↔ `assistant`가 번갈아 등장
```json
{
  "messages": [
    { "role": "user", "content": "1+1은?" },
    { "role": "assistant", "content": "2입니다!" }
  ]
}
```

### 2-3. Unsloth로 채팅 템플릿 적용

ChatML 형식 데이터셋은 4단계로 준비합니다.

```python
# 1. 지원 템플릿 확인
from unsloth.chat_templates import CHAT_TEMPLATES
print(list(CHAT_TEMPLATES.keys()))
# ['unsloth','chatml','mistral','llama-3.1','qwen2.5','gemma-3', ...]

# 2. 토크나이저에 템플릿 적용
from unsloth.chat_templates import get_chat_template
tokenizer = get_chat_template(tokenizer, chat_template="gemma-3")

# 3. 포맷팅 함수 정의
def formatting_prompts_func(examples):
    convos = examples["conversations"]
    texts = [tokenizer.apply_chat_template(c, tokenize=False, add_generation_prompt=False) for c in convos]
    return {"text": texts}

# 4. 데이터셋 로드 + 적용
from datasets import load_dataset
dataset = load_dataset("repo_name/dataset_name", split="train")
dataset = dataset.map(formatting_prompts_func, batched=True)
```

> **ShareGPT → ChatML 변환:** `from`/`value` 형식이면 `standardize_sharegpt(dataset)`로 먼저 변환 후 적용합니다.
>
> **다중 컬럼 병합:** Titanic처럼 컬럼이 많은 CSV는 `to_sharegpt`로 여러 컬럼을 하나의 프롬프트로 병합합니다. 컬럼은 `{}`로 감싸고, 결측치가 있을 수 있는 선택 항목은 `[[ ]]`로 감싸면 빈 값일 때 자동 제외됩니다.
>
> **단일 턴 → 다중 턴 확장:** `conversation_extension` 파라미터로 단일 턴 행 여러 개를 무작위로 묶어 다중 턴 대화로 만들 수 있습니다.

### 2-4. 합성 데이터 생성 (Synthetic Data)

로컬 LLM(Llama 3.3 70B 등)이나 GPT로 데이터를 합성할 수 있습니다. 큰 모델일수록 품질이 좋습니다. 3가지 목표:

- **신규 생성:** 처음부터 또는 기존 데이터 기반으로 새 데이터 생성
- **다양화:** 과적합(overfitting) 방지를 위한 다양성 확보
- **증강:** 기존 데이터를 올바른 포맷으로 자동 구조화

**예시 프롬프트**
- 기존 데이터셋 확장: `제공한 예시 구조를 따라 대화를 생성해줘`
- 데이터가 없을 때: `코카콜라 제품 리뷰 10개를 긍정/부정/중립으로 분류해 만들어줘`
- 포맷이 없을 때: `내 데이터셋을 QA ChatML 포맷으로 구조화한 뒤 같은 주제·포맷으로 5개 합성 예시를 생성해줘`

> 최소 10개 이상의 예시를 먼저 제공해야 모델이 구조와 맥락을 학습합니다.

---

## 3. Unsloth Data Recipes (노코드 워크플로우)

PDF·CSV·DOCX 등 문서를 업로드하면 그래프-노드 워크플로우로 데이터셋을 시각적으로 만들고 편집하는 기능입니다. **NVIDIA NeMo Data Designer** 기반으로 동작합니다.

### 전체 흐름

1. Recipes 페이지 열기
2. 새 레시피 생성 또는 기존 레시피 열기 (빈 레시피 / 학습용 예제 레시피)
3. 블록을 추가해 데이터셋 워크플로우 정의
4. **Validate** 클릭 → 설정 오류를 조기에 잡기
5. **Preview** 실행 → 샘플 행을 빠르게 확인
6. 준비되면 전체 데이터셋 빌드 실행
7. 그래프 또는 **Executions** 뷰에서 진행 상황·출력 실시간 확인
8. Studio에서 결과 데이터셋을 선택해 모델 파인튜닝

### 주요 블록

| 블록 | 역할 |
|------|------|
| **Seed** | HF 데이터셋·로컬 구조화 파일·비구조화 문서(청크 분할)에서 입력 데이터 공급 |
| **LLM + Models** | 프로바이더·모델 설정·LLM 생성 블록·툴 프로필 |
| **Expression** | LLM 호출 없이 Jinja2 기반 변환 수행 |
| **Validators** | Python·SQL·JS/TS 린터로 잘못된 생성 코드 필터링 |
| **Samplers** | 카테고리·서브카테고리 등 결정론적 컬럼 생성 |

**4가지 LLM 블록 유형**

| 블록 | 출력 | 용도 |
|------|------|------|
| LLM Text | 자유 텍스트 | 지시문·설명·대화·서술 |
| LLM Structured | JSON | 고정 필드·예측 가능한 구조 출력 |
| LLM Code | 코드 | Python·SQL·TS 등 코드 생성 |
| **LLM Judge** | 점수 평가 | 사용자 정의 점수로 출력 채점 |

---

## 4. 데이터 검증 방법 (핵심)

Unsloth는 데이터셋을 만드는 **과정 중간중간에** 검증하도록 설계되어 있습니다. 권장 패턴은 **"검증 우선 → 미리보기 → 개선 → 전체 실행"** 의 반복 루프입니다.

### 4-1. Data Recipes의 4단계 실행 루프

```
Validate ──► Preview ──► Refine ──► Run (Full Build)
   ▲                          │
   └──────── 반복 ◄───────────┘
```

| 단계 | 내용 |
|------|------|
| **① Validate** | **Validate** 버튼으로 설정 오류(블록 연결·참조·프롬프트 등)를 본격 실행 전에 잡아냄 |
| **② Preview** | 미리보기 실행 — 샘플 행과 분석 결과를 에디터에서 즉시 확인 (전체 실행 전 빠른 점검) |
| **③ Refine** | 프롬프트·참조·시드 설정·Validator를 다듬으며 만족할 때까지 반복 |
| **④ Run** | 결과가 계획에 부합하면 전체 데이터셋 빌드 실행 → 로컬 데이터셋 아티팩트로 영구 저장 |

> Preview는 빠른 반복용이고, Full Run은 영구 저장된 데이터셋을 만들어 Studio의 로컬 데이터셋 선택기에 나타납니다. (선택 시 Hugging Face 저장소에 게시 가능)

### 4-2. Validator 블록 (자동 코드 검증)

- 주로 **LLM Code 블록**을 대상으로, 생성된 코드 출력을 **린터(Linter)와 구문(Syntax) 검사**에 통과시킵니다.
- 잘못되거나 유효하지 않은 코드 행을 **자동으로 걸러내** 최종 데이터셋에서 제외합니다.
- 내장 지원: **Python, SQL, JavaScript/TypeScript**

### 4-3. LLM Judge 블록 (품질 채점)

- 생성된 출력을 사용자가 정의한 하나 이상의 점수 기준으로 채점합니다.
- 품질이 낮은 행을 식별·필터링하거나, 점수에 따라 데이터셋을 선별하는 데 활용합니다.

### 4-4. 합성 데이터의 수동 품질 검증

합성 데이터는 추가적인 주의가 필요하며, 다음을 권장합니다.

- **품질 점검:** 생성된 데이터의 품질을 확인하고, 관련 없거나 품질이 낮은 응답을 제거·개선합니다.
- **밸런싱:** 데이터가 한쪽으로 치우치지 않도록 여러 영역에서 균형을 맞춰 **과적합을 방지**합니다.
- **재생성 루프:** 정제된 데이터셋을 다시 LLM에 넣어, 더 강화된 가이드로 데이터를 재생성합니다.

### 4-5. 데이터셋 크기·구조 검증 기준

| 항목 | 권장 기준 |
|------|-----------|
| 최소 분량 | **최소 100행** (합리적 결과의 하한선) |
| 권장 분량 | **1,000행 이상** (많을수록 일반적으로 더 좋은 결과) |
| 분량 부족 시 | 합성 데이터 추가 또는 HF 데이터셋으로 다양화 |
| 핵심 원칙 | 분량보다 **품질**이 중요 — 철저한 정제·준비 필수 |

**구조 검증 체크리스트**
- 깔끔하게 토크나이즈 가능한가
- 역할 태깅(user vs assistant)이 정확한가 — 잘못되면 모델이 입력과 응답을 혼동해 환각·오답 발생
- 채팅 템플릿이 모델 기대 형식과 일치하는가
- 포맷(ChatML/ShareGPT/Alpaca 등)이 **전체 데이터셋에서 일관**되는가

---

## 5. 추론(Reasoning) 모델용 데이터 구조

- **이미 추론 능력이 있는 모델**(예: DeepSeek-R1-Distill-Llama-8B) 파인튜닝: 질문/답변 쌍을 유지하되, 답변에 **사고 과정(chain-of-thought)과 도출 단계**를 포함시킵니다.
- **추론 능력이 없는 모델에 추론을 학습**시키려는 경우: 답변에 추론이 없는 표준 데이터셋을 사용하고, **강화학습(GRPO)** 방식으로 훈련합니다.

---

## 6. 요약: 생성 → 검증 전체 파이프라인

```
[1] 목적·스타일·소스 식별
        │
[2] 데이터 수집 (CSV/PDF/웹/HF/합성)
        │
[3] 포맷팅 (Raw / Alpaca / ShareGPT / ChatML)
        │
[4] 채팅 템플릿 적용 (get_chat_template, standardize_sharegpt)
        │
┌───────▼────────  검증 루프  ────────────┐
│  Validate → Preview → Refine            │
│  · Validator 블록 (Python/SQL/JS 린터)  │
│  · LLM Judge (품질 채점)                │
│  · 수동 품질·밸런싱 점검                 │
│  · 크기(≥100, 권장 ≥1,000)·구조 검증     │
└───────┬─────────────────────────────────┘
        │ (만족 시)
[5] Full Run → 로컬 데이터셋 아티팩트 저장
        │
[6] Studio에서 파인튜닝 / (선택) HF 게시
```

---

### 참고 링크
- Datasets Guide: https://unsloth.ai/docs/get-started/fine-tuning-llms-guide/datasets-guide
- Unsloth Data Recipes: https://unsloth.ai/docs/new/studio/data-recipe
- NVIDIA NeMo Data Designer: https://github.com/NVIDIA-NeMo/DataDesigner
