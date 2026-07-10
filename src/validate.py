# STEP7 검증 루프: Validator·LLM Judge·근거성·크기/구조 점검 (TRD §5)
import re

from .config import config
from .schemas import validate_instruction, validate_qa, validate_rag


def _tokens(s: str) -> set:
    return set(re.findall(r"[가-힣A-Za-z]{2,}", s or ""))


def _grounding(output: str, source: str) -> float:
    # output이 원문(source=input 청크)의 어휘를 얼마나 공유하는지(0~1). 근거성 신호.
    ot = _tokens(output)
    if not ot:
        return 0.0
    return round(len(ot & _tokens(source)) / len(ot), 3)


# 방법론 Entity 검증 — 법률 도메인 핵심 엔티티. output이 만들어낸 사실(조문·금액·날짜·
# 법령명·기관명)이 원문에 실재하는지 대조해 근거성·환각을 정량화한다(모델 불필요, 망분리 안전).
_ENTITY_PATTERNS = [
    re.compile(r"제\s?\d+\s?조(?:의\s?\d+)?(?:제\s?\d+\s?항)?(?:제\s?\d+\s?호)?"),  # 조문
    re.compile(r"\d[\d,]*\s?[억조천만]*\s?원"),                     # 금액(3천만원·500만원·3억원)
    re.compile(r"\d{4}\s?\.\s?\d{1,2}\s?\.\s?\d{1,2}"),             # 날짜
    re.compile(r"「[^」]+」|『[^』]+』"),                            # 법령명
    re.compile(r"[가-힣]{2,}(?:부장관|위원회|위원장|공단|공사|조합|재단|본부|장관|청장|처)"),  # 기관명
]


def _entities(s: str) -> set:
    ents = set()
    for p in _ENTITY_PATTERNS:
        for m in p.finditer(s or ""):
            ents.add(re.sub(r"\s+", "", m.group()))
    return ents


def _entity_grounding(output: str, source: str):
    # output의 핵심 엔티티 중 원문(source)에 실재하는 비율과, 원문에 없는(환각 의심) 엔티티.
    # 엔티티가 없는 output(일반 설명 등)은 판정에서 제외한다(None 반환).
    oe = _entities(output)
    if not oe:
        return None, []
    src = re.sub(r"\s+", "", source or "")
    unsupported = sorted(e for e in oe if e not in src)
    return round((len(oe) - len(unsupported)) / len(oe), 3), unsupported


def run_validation(datasets: dict, unsloth: dict, records: list, llm=None) -> dict:
    issues = []

    # 1) Validator — 스키마/구조 무효 행 제외
    clean_inst = [d for d in datasets["instruction"] if validate_instruction(d)]
    clean_qa = [d for d in datasets["qa"] if validate_qa(d)]
    clean_rag = [d for d in datasets["rag"] if validate_rag(d)]

    # 2) 중복 제거 (원문 근거·중복 검증)
    seen = set()
    deduped = []
    for r in records:
        key = (r["question"], r["answer"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    dup_removed = len(records) - len(deduped)

    # 3) 포맷 일관성 — 역할 태깅 교대 검사
    format_ok = _check_roles(unsloth)
    if not format_ok:
        issues.append("ChatML/ShareGPT 역할 태깅 교대 불일치")

    # 4) 크기 기준 — 합성 패딩을 제거했으므로 소스가 작으면 행 수가 적을 수 있다.
    #    크기 미달은 PASS를 막는 하드 게이트가 아니라 경고로 둔다(해법은 소스 확대).
    row_count = len(deduped)
    size_ok = row_count >= config.min_rows
    if not size_ok:
        issues.append(f"경고: 행 수 {row_count} < 권장 최소 {config.min_rows} (소스 문서 확대 권장)")

    # 5) LLM Judge (자체 휴리스틱 채점) — 빈 답변·과단문 감점
    judged = [r for r in deduped if len(r["answer"]) >= 8]
    quality_filtered = len(deduped) - len(judged)

    quality_score = _score(judged, format_ok)
    status = "PASS" if quality_score >= config.quality_pass_score else "FAIL"

    # 6) 근거성(grounding) — 각 레코드 output이 원문(input)에 근거하는지 점수·플래그로
    #    레코드에 저장한다(감사 추적성). 법률 도메인은 오답 비용이 커 저근거를 명시적으로 표시.
    for r in judged:
        g = _grounding(r["output"], r["input"])
        r["grounding"] = g
        r["grounded"] = g >= config.grounding_min
    mean_grounding = round(sum(r["grounding"] for r in judged) / len(judged), 3) if judged else 0.0
    low_grounding = sum(1 for r in judged if not r["grounded"])
    if judged and mean_grounding < config.grounding_min:
        issues.append(f"경고: 평균 근거성 {mean_grounding} < 기준 {config.grounding_min} (원문 근거 확인 권장)")

    # 7) Entity 검증·환각(방법론) — output의 핵심 엔티티가 원문에 실재하는지 대조한다.
    #    대조 대상은 해당 청크가 아니라 '같은 소스 문서 전체'(그 문서의 모든 청크 합집합)로
    #    한다. 조문 참조가 다른 청크에 있어도 문서엔 존재하므로 환각으로 오탐하지 않는다.
    corpus = {}
    for r in judged:
        corpus.setdefault(r["source_document"], []).append(r["input"])
    corpus = {k: " ".join(v) for k, v in corpus.items()}
    for r in judged:
        doc = corpus.get(r["source_document"], r["input"])
        eg, unsupported = _entity_grounding(r["output"], doc)
        r["entity_grounding"] = eg
        r["hallucinated_entities"] = unsupported  # 문서 전체에 없는 엔티티(환각 의심)
    scored = [r for r in judged if r["entity_grounding"] is not None]
    entity_grounding = round(sum(r["entity_grounding"] for r in scored) / len(scored), 3) if scored else None
    halluc_records = sum(1 for r in judged if r["hallucinated_entities"])
    hallucination_rate = round(halluc_records / len(judged) * 100, 1) if judged else 0.0

    # 8) 의미 보존(방법론) — 임베딩 모델이 있고 활성화된 경우에만 표본으로 측정한다.
    mean_semantic = None
    if config.semantic_enabled and judged:
        from . import semantic
        sims = [s for s in (semantic.semantic_similarity(r["output"], r["input"])
                            for r in judged[:config.semantic_sample]) if s is not None]
        mean_semantic = round(sum(sims) / len(sims), 3) if sims else None

    # 9) RAGAS 스타일 자동평가(LLM 심판) — faithfulness(원문 근거)·answer_relevancy(질문 적합).
    #    라이브러리 대신 로컬 LLM으로 핵심 지표만 계산한다(옵인·표본).
    ragas = None
    if config.ragas_enabled and judged and llm is not None and llm.available():
        ragas = _ragas_scores(judged[:config.ragas_sample], llm)

    # 10) 메타데이터 완전성(방법론 100%)·중복률·최종 등급·Human Review 표본.
    dup_rate = round(dup_removed / len(records) * 100, 1) if records else 0.0
    metadata_complete = all(
        r.get("source_document") and r.get("keyword") for r in judged
    ) if judged else False
    grade = _grade(quality_score)
    review_ids = [r["id"] for r in _review_sample(judged, config.human_review_rate)]

    return {
        "quality_score": quality_score,
        "status": status,
        "grade": grade,
        "row_count": len(judged),
        "duplicates_removed": dup_removed,
        "duplicate_rate": dup_rate,
        "quality_filtered": quality_filtered,
        "format_consistent": format_ok,
        "size_ok": size_ok,
        "mean_grounding": mean_grounding,
        "low_grounding": low_grounding,
        "entity_grounding": entity_grounding,
        "hallucination_rate": hallucination_rate,
        "mean_semantic": mean_semantic,
        "ragas": ragas,
        "metadata_complete": metadata_complete,
        "review_ids": review_ids,
        "issues": issues,
        "records": judged,
    }


def _ragas_scores(records: list, llm) -> dict:
    # RAGAS 스타일 지표를 로컬 LLM 심판으로 계산한다(라이브러리 미사용). 표본별로
    # faithfulness(답이 원문 근거에 부합하는가)·answer_relevancy(답이 질문에 맞는가)를
    # 0~1로 받아 평균낸다. 파싱 실패 표본은 제외한다.
    faith, rel = [], []
    for r in records:
        data = llm.generate_json(
            "아래 [근거]에 비추어 [답변]을 평가하라. 0.0~1.0 실수로만 채점한다.\n"
            "- faithfulness: 답변 내용이 근거에서 뒷받침되는 정도(환각이면 낮게)\n"
            "- answer_relevancy: 답변이 질문에 적절히 답하는 정도\n"
            '반드시 JSON만: {"faithfulness":0.0,"answer_relevancy":0.0}\n\n'
            f"[질문]\n{r.get('question','')}\n\n[근거]\n{r['input']}\n\n[답변]\n{r['output']}",
            system="너는 엄격한 데이터셋 품질 평가자다. 근거에 없으면 낮게 준다.",
        )
        if not isinstance(data, dict):
            continue
        try:
            f = float(data.get("faithfulness"))
            a = float(data.get("answer_relevancy"))
        except (TypeError, ValueError):
            continue
        faith.append(max(0.0, min(1.0, f)))
        rel.append(max(0.0, min(1.0, a)))
    if not faith:
        return None
    return {
        "faithfulness": round(sum(faith) / len(faith), 3),
        "answer_relevancy": round(sum(rel) / len(rel), 3),
        "sampled": len(faith),
    }


def _review_sample(records: list, rate: float) -> list:
    # Human Review 표본(방법론 5~10%). 위험도 높은 레코드를 우선 선정한다:
    # 환각 의심 > 저근거 > 낮은 엔티티 근거성 > 낮은 어휘 근거성.
    if not records:
        return []
    target = max(1, round(len(records) * rate))

    def risk(r):
        eg = r.get("entity_grounding")
        return (
            1 if r.get("hallucinated_entities") else 0,
            0 if r.get("grounded", True) else 1,
            1 - (eg if eg is not None else 1.0),
            1 - (r.get("grounding") or 0.0),
        )

    return sorted(records, key=risk, reverse=True)[:target]


def _grade(score: int) -> str:
    # 방법론 최종 품질 등급: 90+ A, 80+ B, 70+ C, 그 외 D.
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    return "D"


def _check_roles(unsloth: dict) -> bool:
    # 대화형 포맷은 system=지시, user=원문, assistant=출력의 3턴이다(보고서 2-2 대응).
    for c in unsloth.get("chatml", []):
        roles = [m["role"] for m in c["messages"]]
        if roles != ["system", "user", "assistant"]:
            return False
    for c in unsloth.get("sharegpt", []):
        froms = [m["from"] for m in c["conversations"]]
        if froms != ["system", "human", "gpt"]:
            return False
    return True


def _score(rows, format_ok) -> int:
    # 품질 점수는 형식 일관성과 답변 충실도로만 매긴다. 행 수(크기)는 경고 대상이지
    # 품질 점수 감점 요소가 아니다(소스가 작아도 내용이 좋으면 고품질).
    if not rows:
        return 0
    base = 100
    if not format_ok:
        base -= 30
    # 너무 짧은 답변 비율 감점
    short = sum(1 for r in rows if len(r["answer"]) < 15)
    base -= int(10 * short / len(rows))
    return max(0, min(100, base))
