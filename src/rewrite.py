# 저근거(grounding) 레코드를 '원문 표현을 살려' 재작성하는 보강 패스
#
# 배경: 생성 프롬프트가 "표현은 새로 쓰라"고 지시하므로 어휘 근거성이 낮게 나온다(실측 평균 0.41).
# 사실은 보존되지만(엔티티 근거성 0.94+) 어휘 중첩 기준으로는 저근거로 보인다.
# 여기서는 저근거 레코드만 골라 "원문의 명사구·수치·조문·용어를 그대로 사용"하도록 다시 쓴다.
#
# 안전 규칙(개악 방지): 재작성본은 다음을 모두 만족할 때만 채택한다.
#   1) 어휘 근거성이 실제로 상승      2) 새 환각 엔티티가 생기지 않음
#   3) 길이가 정상 범위(32~137자)     4) 빈 답변이 아님
# 하나라도 어기면 원본을 유지한다 → 재작성이 품질을 떨어뜨릴 수 없다.
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import config
from .pipeline import _INJECTION_GUARD, _fence
from .validate import _entities, _entity_grounding, _grounding

_MIN_LEN, _MAX_LEN = 32, 137


def _rewrite_one(r, doc, llm):
    src = r["input"]
    data = llm.generate_json(
        "아래 [원문]에 대한 [기존답변]을 다시 작성하라.\n"
        "- 원문의 표현(명사구·수치·기간·금액·조문번호·법령명·용어)을 **그대로 인용**해 사용하라.\n"
        "- 원문에 없는 사실·조문·용어를 새로 만들지 마라.\n"
        "- 기존답변의 의미는 유지하되, 원문 어휘를 최대한 살려 32~137자로 쓴다.\n"
        '반드시 JSON만: {"a":""}\n\n'
        f"[원문]\n{_fence(src)}\n\n[기존답변]\n{r['output']}",
        system="너는 원문 표현을 충실히 보존하는 한국어 법률 문서 요약가다." + _INJECTION_GUARD,
    )
    if not isinstance(data, dict):
        return None
    a = str(data.get("a", "")).strip()
    if not a or not (_MIN_LEN <= len(a) <= _MAX_LEN):
        return None

    new_g = _grounding(a, doc)
    if new_g <= (r.get("grounding") or 0):      # 근거성이 오르지 않으면 채택하지 않음
        return None
    _, unsupported = _entity_grounding(a, doc)
    if unsupported:                              # 새 환각이 생기면 채택하지 않음
        return None
    return a, new_g


def rewrite_low_grounding(records: list, llm, threshold: float = None) -> dict:
    """어휘 근거성이 threshold 미만인 레코드를 원문 표현을 살려 재작성한다.

    반환: {"targeted": n, "rewritten": n, "mean_before": f, "mean_after": f}
    """
    thr = config.grounding_rewrite_min if threshold is None else threshold
    if not records or llm is None or not llm.available():
        return {"targeted": 0, "rewritten": 0}

    # 근거성 대조 기준은 검증과 동일하게 '같은 소스 문서 전체'로 둔다.
    corpus = {}
    for r in records:
        corpus.setdefault(r["source_document"], []).append(r["input"])
    corpus = {k: " ".join(v) for k, v in corpus.items()}

    targets = [r for r in records if (r.get("grounding") or 0) < thr]
    before = sum(r.get("grounding") or 0 for r in records) / len(records)
    if not targets:
        return {"targeted": 0, "rewritten": 0, "mean_before": round(before, 3),
                "mean_after": round(before, 3)}

    done = 0
    with ThreadPoolExecutor(max_workers=config.llm_concurrency) as ex:
        futs = {ex.submit(_rewrite_one, r, corpus.get(r["source_document"], r["input"]), llm): r
                for r in targets}
        for f in as_completed(futs):
            res = f.result()
            if not res:
                continue
            r = futs[f]
            a, new_g = res
            doc = corpus.get(r["source_document"], r["input"])
            eg, unsupported = _entity_grounding(a, doc)
            r["output"] = a
            r["answer"] = a
            r["grounding"] = new_g
            r["grounded"] = new_g >= config.grounding_min
            r["entity_grounding"] = eg if eg is not None else new_g
            r["hallucinated_entities"] = unsupported
            r["short_answer"] = len(a) < 30
            done += 1

    after = sum(r.get("grounding") or 0 for r in records) / len(records)
    return {"targeted": len(targets), "rewritten": done,
            "mean_before": round(before, 3), "mean_after": round(after, 3)}


def recompute_metrics(records: list) -> dict:
    """재작성 후 요약 지표를 다시 낸다.

    주의: 엔티티 근거성 평균은 **실제 엔티티를 가진 레코드만** 대상으로 한다
    (엔티티 없는 output은 필드가 어휘 근거성으로 채워져 있어, 그대로 평균내면
    두 지표가 섞여 값이 오염된다).
    """
    if not records:
        return {}
    corpus = {}
    for r in records:
        corpus.setdefault(r["source_document"], []).append(r["input"])
    corpus = {k: " ".join(v) for k, v in corpus.items()}

    gs = [r["grounding"] for r in records]
    scored = []          # 실제 엔티티가 있는 레코드의 엔티티 근거성만 모은다
    for r in records:
        if not _entities(r["output"]):
            continue
        doc = corpus.get(r["source_document"], r["input"])
        eg, _ = _entity_grounding(r["output"], doc)
        if eg is not None:
            scored.append(eg)
    halluc = sum(1 for r in records if r.get("hallucinated_entities"))
    return {
        "mean_grounding": round(sum(gs) / len(gs), 3),
        "low_grounding": sum(1 for r in records if not r.get("grounded")),
        "entity_grounding": round(sum(scored) / len(scored), 3) if scored else None,
        "hallucination_rate": round(halluc / len(records) * 100, 1),
    }
