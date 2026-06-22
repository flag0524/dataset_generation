# 8단계 데이터셋 생성 파이프라인의 각 STEP 구현 (TRD §1 아키텍처)
import re
from datetime import date

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


def _segments(text: str):
    # 문단/문장 단위로 텍스트를 의미 청크로 분해
    parts = re.split(r"\n\s*\n", text)
    segs = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        for s in re.split(r"(?<=[.!?。])\s+|\n", p):
            s = s.strip(" -*#\t")
            if len(s) >= 8:
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


def _top_keywords(text: str, n: int = 10):
    words = re.findall(r"[가-힣A-Za-z]{2,}", text)
    freq = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:n]]


# ---------- STEP 2. 전문가 라우팅 ----------
def route_expert(domain: str) -> str:
    return EXPERT_ROUTING.get(domain, EXPERT_ROUTING["일반"])


# ---------- STEP 3. 지식·규칙 추출 ----------
# 추출 지식 7항목 (TRD §4.2)
KNOWLEDGE_FIELDS = ["업무정의", "업무목적", "처리절차", "담당조직", "입력데이터", "처리규칙", "결과데이터"]


def extract_knowledge(text: str, meta: dict, llm: LLMClient) -> dict:
    # gemma4 LLM 우선, 실패/미가용 시 휴리스틱 폴백
    segs = _segments(text)
    result = _llm_extract(text, meta, llm)
    if result is None:
        result = _heuristic_extract(segs, meta)
        result["extraction_mode"] = "heuristic"
    else:
        result["extraction_mode"] = "llm"
    result["segments"] = segs  # 하위 단계(STEP4)의 커버리지 확보용
    return result


def _llm_extract(text: str, meta: dict, llm: LLMClient):
    if not llm.available():
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
    data = llm.generate_json(prompt, system)
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
def generate_datasets(text: str, meta: dict, extracted: dict, llm: LLMClient) -> dict:
    instructions, qas, rags = [], [], []
    expert = route_expert(meta["domain"])
    src = meta["document_name"]
    for i, seg in enumerate(extracted["segments"]):
        q = f"{seg[:30]}에 대해 설명하라."
        instructions.append({
            "instruction": f"{expert} 관점에서 다음 내용을 설명하라.",
            "input": seg[:40],
            "output": seg,
        })
        qas.append({"question": q, "answer": seg, "source": src})
        rags.append({
            "id": f"DOC-{i+1:04d}",
            "title": seg[:30],
            "content": seg,
            "metadata": {"keyword": meta["keywords"][:3]},
        })
    return {"instruction": instructions, "qa": qas, "rag": rags}


# ---------- STEP 4.5 Unsloth 포맷 변환 ----------
def to_unsloth_formats(datasets: dict) -> dict:
    raw = [{"text": d["output"]} for d in datasets["instruction"]]
    alpaca = [
        {"Instruction": d["instruction"], "Input": d["input"], "Output": d["output"]}
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
