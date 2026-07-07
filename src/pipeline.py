# 8단계 데이터셋 생성 파이프라인의 각 STEP 구현 (TRD §1 아키텍처)
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from .config import config
from .llm import LLMClient

# STEP2 도메인 → 전문가 역할 라우팅 테이블 (TRD §6)
EXPERT_ROUTING = {
    "공공행정": "지방행정 전문가",
    "법률": "법률 분석 전문가",
    "금융": "금융 업무 전문가",
    "일반": "도메인 전문가",
}

DOMAIN_KEYWORDS = {
    "공공행정": ["행정", "지자체", "민원", "조례", "공공", "행정안전"],
    "법률": ["법률", "조항", "판례", "계약", "소송", "법령"],
    "금융": ["금융", "대출", "예금", "투자", "이자", "계좌"],
}


def _budget_timeout(deadline):
    # LLM 호출에 쓸 타임아웃을 deadline(monotonic 기준)으로 결정한다.
    # 반환 (use_llm, timeout):
    #   deadline 없음        → (True, None)   예산 제한 없음, 기본 타임아웃
    #   남은 시간 > 1초      → (True, 남은초)  남은 예산만큼만 기다림
    #   임박/초과(≤1초)      → (False, None)  LLM 건너뛰고 휴리스틱 폴백
    if deadline is None:
        return True, None
    remaining = deadline - time.monotonic()
    if remaining > 1:
        return True, remaining
    return False, None


# 목차 점선(dot leader)·페이지번호·구분선 등 비의미 청크를 걸러내는 패턴.
_NOISE_PATTERNS = [
    re.compile(r"^[\s.·․…‥∙⋯\-—_=]+$"),   # 점선/구분선만 있는 줄
    re.compile(r"^\d+\s*$"),                  # 페이지 번호만
    re.compile(r"^[-\s]*\d+[-\s]*$"),         # - 12 - 형태 페이지 번호
]
_MIN_SEG_LEN = 15  # 문장 조각·목차 잔재를 걸러내는 최소 길이


def _is_noise(s: str) -> bool:
    # 목차 점선·페이지번호 등 학습 가치 없는 청크인지 판별한다.
    if any(p.match(s) for p in _NOISE_PATTERNS):
        return True
    # 점선(dot leader)이 대부분을 차지하는 목차 항목 (예: "제안경위 ·········· 3")
    dots = sum(s.count(c) for c in ".·․…‥∙⋯")
    return dots >= 6 and dots >= len(s) * 0.3


def _segments(text: str):
    # 문서를 의미 있는 문장 청크로 분해한다. PDF 추출 텍스트는 문장 중간에서 줄바꿈되므로,
    # 먼저 문단 내 줄바꿈을 공백으로 이어 붙여 문장이 중간에서 잘리지 않게 한 뒤,
    # 문장 경계(마침표·물음표 등)로만 분할한다. 목차 점선·페이지번호는 걸러낸다.
    parts = re.split(r"\n\s*\n", text)
    segs = []
    for p in parts:
        # 문단 내 단일 줄바꿈은 문장 연속으로 보고 공백으로 결합(중간 잘림 방지).
        joined = re.sub(r"\s*\n\s*", " ", p).strip()
        if not joined:
            continue
        for s in re.split(r"(?<=[.!?。])\s+", joined):
            s = s.strip(" -*#\t·")
            if len(s) >= _MIN_SEG_LEN and not _is_noise(s):
                segs.append(s)
    return segs


# ---------- STEP 1. 문서 분석 ----------
def analyze(text: str, document_name: str, llm: LLMClient) -> dict:
    domain = _classify_domain(text)
    keywords = _top_keywords(text)
    purpose = _segments(text)[0] if _segments(text) else ""
    return {
        "document_name": document_name,
        "domain": domain,
        "purpose": purpose[:120],
        "keywords": keywords,
    }


def _classify_domain(text: str) -> str:
    scores = {d: sum(text.count(k) for k in kws) for d, kws in DOMAIN_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "일반"


# 키워드에서 제외할 한국어 불용어(조사·접속사·의존명사·형식어). 형태소 분석기 없이
# (망분리) 빈도 상위에 올라오는 조사/접속사류를 제거해 의미 키워드만 남긴다.
_STOPWORDS = {
    "또는", "관한", "관하여", "대한", "대하여", "위한", "위하여", "그리고", "그러나", "따라",
    "따른", "따라서", "이하", "이상", "경우", "때문", "통해", "통하여", "및", "등", "등의",
    "기준", "관련", "해당", "각각", "모든", "어느", "다음", "같은", "있는", "없는", "하는",
    "되는", "이러한", "그러한", "우리", "본", "제", "그", "이", "저", "것", "수", "바",
    "한다", "된다", "했다", "하고", "하여", "하며", "된", "하는데", "이다", "있다", "없다",
}


def _top_keywords(text: str, n: int = 10):
    # 2자 이상 한글/영문 토큰 빈도 상위 n개. 단 조사·접속사류 불용어는 제외한다.
    words = re.findall(r"[가-힣A-Za-z]{2,}", text)
    freq = {}
    for w in words:
        if w in _STOPWORDS:
            continue
        freq[w] = freq.get(w, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:n]]


# ---------- STEP 2. 전문가 라우팅 ----------
def route_expert(domain: str) -> str:
    return EXPERT_ROUTING.get(domain, EXPERT_ROUTING["일반"])


# ---------- STEP 3. 지식·규칙 추출 ----------
# 추출 지식 7항목 (TRD §4.2)
KNOWLEDGE_FIELDS = ["업무정의", "업무목적", "처리절차", "담당조직", "입력데이터", "처리규칙", "결과데이터"]


def extract_knowledge(text: str, meta: dict, llm: LLMClient, deadline=None) -> dict:
    # gemma4 LLM 우선, 실패/미가용 시 휴리스틱 폴백
    segs = _segments(text)
    result = _llm_extract(text, meta, llm, deadline)
    if result is None:
        result = _heuristic_extract(segs, meta)
        result["extraction_mode"] = "heuristic"
    else:
        result["extraction_mode"] = "llm"
    result["segments"] = segs  # 하위 단계(STEP4)의 커버리지 확보용
    return result


def _llm_extract(text: str, meta: dict, llm: LLMClient, deadline=None):
    if not llm.available():
        return None
    use_llm, timeout = _budget_timeout(deadline)
    if not use_llm:
        return None
    expert = route_expert(meta["domain"])
    system = f"너는 {expert}이자 AI 데이터 엔지니어다. 문서에서 업무 지식과 규칙을 구조화한다."
    prompt = (
        f"다음 문서를 분석하여 업무 지식과 처리 규칙을 추출하라.\n"
        f"- knowledge: {', '.join(KNOWLEDGE_FIELDS)} 키를 가진 객체. 각 값은 문서 근거 기반의 한국어 설명.\n"
        f"- rules: 각 항목은 rule_id(R001 형식), condition(조건), action(조치), exception(예외) 키를 가진 배열.\n"
        f"반드시 아래 형식의 JSON만 출력하라.\n"
        f'{{"knowledge": {{...}}, "rules": [{{"rule_id":"R001","condition":"","action":"","exception":""}}]}}\n\n'
        f"[문서]\n{text[:6000]}"
    )
    data = llm.generate_json(prompt, system, timeout=timeout)
    rules = _normalize_rules(data.get("rules"))
    knowledge = data.get("knowledge")
    # LLM 응답이 규칙·지식 중 하나라도 유효해야 채택, 아니면 폴백
    if not rules or not isinstance(knowledge, dict):
        return None
    knowledge = {k: knowledge.get(k, "") for k in KNOWLEDGE_FIELDS}
    return {"knowledge": knowledge, "rules": rules}


def _normalize_rules(rules):
    if not isinstance(rules, list):
        return []
    out = []
    for i, r in enumerate(rules):
        if not isinstance(r, dict) or not r.get("condition"):
            continue
        out.append({
            "rule_id": r.get("rule_id") or f"R{i+1:03d}",
            "condition": str(r.get("condition", "")),
            "action": str(r.get("action", "")) or "규정 적용",
            "exception": str(r.get("exception", "")),
        })
    return out


def _heuristic_extract(segs, meta):
    rules = []
    for i, s in enumerate(segs):
        if re.search(r"(해야|하면|경우|시|불가|금지|필수|이내|초과)", s):
            rules.append({
                "rule_id": f"R{i+1:03d}",
                "condition": s,
                "action": "규정 적용",
                "exception": "",
            })
    knowledge = {
        "업무정의": meta["purpose"],
        "업무목적": meta["purpose"],
        "처리절차": segs,
        "담당조직": meta["domain"],
        "입력데이터": "",
        "처리규칙": [r["condition"] for r in rules],
        "결과데이터": "",
    }
    return {"knowledge": knowledge, "rules": rules}


# ---------- STEP 4. LLM 데이터셋 생성 ----------
# 한 segment에 적용하는 서로 다른 과제(앵글). instruction/output/question을 모두 다르게 만들어
# input(원문 맥락)과 output(결과물)이 겹치지 않게 한다.
_TASKS = [
    ("{expert} 관점에서 다음 내용을 업무 담당자가 이해하도록 풀어서 설명하라.", "explain"),
    ("다음 내용을 핵심만 한 문장으로 요약하라.", "summarize"),
    ("다음 내용에서 '조건 → 처리' 형태의 업무 처리 기준을 도출하라.", "rule"),
    ("다음 내용의 핵심 용어와 의미를 정리하라.", "terms"),
]

def _derive_outputs(seg: str, meta: dict, expert: str, llm: LLMClient, deadline=None) -> dict:
    # 한 세그먼트의 4개 앵글 결과물을 만들어 유효한 것만 dict로 돌려준다.
    # - 실제 LLM 가용: 1회 호출(JSON) 후 15자 이상인 앵글만 채택. 예산 소진·빈 응답·
    #   저품질 앵글은 폴백 없이 드롭한다(가짜 템플릿이 학습 데이터를 오염하지 않게).
    # - LLM 미가용(mock/테스트): 결정론적 구조 출력으로 파이프라인 end-to-end 보장.
    #   이 출력은 학습용이 아니며 llm_mode=mock으로 표시된다.
    kinds = [k for _, k in _TASKS]
    if not llm.available():
        return {k: _mock_output(k, seg, meta, expert) for k in kinds}
    use_llm, timeout = _budget_timeout(deadline)
    if not use_llm:
        return {}  # 예산 소진 → 이 청크는 드롭
    data = llm.generate_json(
        "다음 내용을 바탕으로 네 가지 결과물을 만들어라. 원문을 그대로 반복하지 말라.\n"
        "- explain: 업무 담당자가 이해하도록 2~3문장 설명\n"
        "- summarize: 한 문장 요약\n"
        "- rule: '조건 → 처리' 형태의 업무 기준 한 문장\n"
        "- terms: 핵심 용어 2~3개와 각 의미\n"
        '반드시 {"explain":"","summarize":"","rule":"","terms":""} 형식의 JSON만 출력하라.\n\n'
        f"내용:\n{seg}",
        system=f"너는 {expert}다. 한국어로 간결하고 정확하게 답하라.",
        timeout=timeout,
    )
    if not isinstance(data, dict):
        return {}
    out = {}
    for k in kinds:
        v = str(data.get(k, "")).strip()
        if len(v) >= 15:  # 유효 앵글만 채택, 나머지는 드롭
            out[k] = v
    return out


def _mock_output(kind: str, seg: str, meta: dict, expert: str) -> str:
    # LLM 미가용(mock/테스트) 전용 결정론적 출력. 실제 LLM 경로에서는 호출되지 않으며
    # 학습용 데이터가 아니다(파이프라인 end-to-end 구동·구조 검증 목적).
    kw = ", ".join(meta["keywords"][:3]) or "핵심 사항"
    if kind == "summarize":
        return f"[mock] 요약하면, 본문은 '{seg[:40]}' 등을 다루는 내용이다."
    if kind == "rule":
        return f"[mock] 처리 기준: '{seg[:40]}' 상황에서 {expert}가 정해진 절차를 적용한다."
    if kind == "terms":
        return f"[mock] 핵심 용어는 {kw}이며, 본문은 이를 중심으로 기술되어 있다."
    return f"[mock] {expert}의 관점에서 보면 이 내용은 다음을 뜻한다 — {seg}."


def _derive_question(kind: str, seg: str) -> str:
    head = seg[:30]
    return {
        "explain": f"{head}의 내용을 설명해 줄 수 있나요?",
        "summarize": f"{head}을(를) 요약하면 무엇인가요?",
        "rule": f"{head}에 적용되는 처리 기준은 무엇인가요?",
        "terms": f"{head}의 핵심 용어는 무엇인가요?",
    }[kind]


def generate_datasets(text: str, meta: dict, extracted: dict, llm: LLMClient, deadline=None) -> dict:
    instructions, qas, rags = [], [], []
    expert = route_expert(meta["domain"])
    src = meta["document_name"]
    segs = extracted["segments"]

    # 세그먼트별 LLM 호출은 I/O 대기(HTTP)라, 스레드풀로 동시에 보내 벽시계 시간을 줄인다.
    # 결과는 인덱스 순서대로 모아 데이터셋 정렬을 유지한다. deadline이 지나면 아직
    # 시작 안 한 작업은 _derive_outputs 안에서 빈 결과가 되어 해당 청크가 드롭된다.
    seg_outputs = [None] * len(segs)
    with ThreadPoolExecutor(max_workers=config.llm_concurrency) as ex:
        futs = {ex.submit(_derive_outputs, seg, meta, expert, llm, deadline): i
                for i, seg in enumerate(segs)}
        for fut in as_completed(futs):
            seg_outputs[futs[fut]] = fut.result()

    for i, seg in enumerate(segs):
        # RAG 패시지는 원문 자체(생성물 아님)라 항상 유지한다.
        rags.append({
            "id": f"DOC-{i+1:04d}",
            "title": seg[:30],
            "content": seg,
            "metadata": {"keyword": meta["keywords"][:3]},
        })
        # instruction/QA는 LLM이 실제로 만든 앵글만 레코드로 만든다(못 만든 앵글은 드롭).
        outputs = seg_outputs[i] or {}
        for tmpl, kind in _TASKS:
            output = outputs.get(kind)
            if not output:
                continue
            instructions.append({
                "instruction": tmpl.format(expert=expert),
                "input": seg,
                "output": output,
            })
            qas.append({"question": _derive_question(kind, seg), "answer": output, "source": src})
    return {"instruction": instructions, "qa": qas, "rag": rags}


# ---------- STEP 4.5 Unsloth 포맷 변환 ----------
def to_unsloth_formats(datasets: dict) -> dict:
    raw = [{"text": d["output"]} for d in datasets["instruction"]]
    # Unsloth/HuggingFace 표준 alpaca 매핑은 소문자 키를 기대한다(대문자면 KeyError 위험).
    alpaca = [
        {"instruction": d["instruction"], "input": d["input"], "output": d["output"]}
        for d in datasets["instruction"]
    ]
    sharegpt = [
        {"conversations": [
            {"from": "human", "value": d["question"]},
            {"from": "gpt", "value": d["answer"]},
        ]}
        for d in datasets["qa"]
    ]
    chatml = [
        {"messages": [
            {"role": "user", "content": d["question"]},
            {"role": "assistant", "content": d["answer"]},
        ]}
        for d in datasets["qa"]
    ]
    return {"raw": raw, "alpaca": alpaca, "sharegpt": sharegpt, "chatml": chatml}


# ---------- STEP 5/6 통합 레코드 ----------
def to_records(meta: dict, datasets: dict) -> list:
    today = date.today().isoformat()
    records = []
    for i, (inst, qa) in enumerate(zip(datasets["instruction"], datasets["qa"])):
        records.append({
            "id": f"{i+1:04d}",
            "domain": meta["domain"],
            "category": "knowledge",
            "question": qa["question"],
            "answer": qa["answer"],
            "instruction": inst["instruction"],
            "input": inst["input"],
            "output": inst["output"],
            "source_document": meta["document_name"],
            "keyword": meta["keywords"][:3],
            "created_date": today,
        })
    return records
