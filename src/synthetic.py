# STEP4 보조: 분량 부족 시 합성 데이터로 증강 (PRD FR-11, Unsloth 가이드 §2-4)
import copy

_PARAPHRASE = [
    ("설명하라", "기술하라"),
    ("에 대해", "에 관하여"),
    ("관점에서", "입장에서"),
]


def dedupe(datasets: dict) -> dict:
    # qa의 (question, answer) 중복을 제거하고 instruction을 같은 인덱스로 정렬 유지한다.
    # rag는 원문 단위(qa/instruction과 길이가 다름)이며 중복이 없으므로 그대로 둔다.
    seen = set()
    keep = []
    for i, q in enumerate(datasets["qa"]):
        key = (q["question"], q["answer"])
        if key in seen:
            continue
        seen.add(key)
        keep.append(i)
    out = dict(datasets)
    out["qa"] = [datasets["qa"][i] for i in keep]
    out["instruction"] = [datasets["instruction"][i] for i in keep]
    return out


def augment(datasets: dict, target: int) -> dict:
    # instruction/qa/rag를 동일 개수로 유지하며 target까지 증강.
    # 이미 존재하는 (question, answer)와 충돌하는 변형은 건너뛰고 변형 번호를
    # 올려 항상 고유 행만 추가한다(증강 결과가 검증 dedup에서 줄지 않도록).
    base = len(datasets["qa"])
    rag_base = len(datasets["rag"])
    if base == 0 or base >= target:
        return datasets
    out = {k: list(v) for k, v in datasets.items()}
    seen = {(q["question"], q["answer"]) for q in out["qa"]}
    idx, variant = 0, 1
    while len(out["qa"]) < target:
        src_i = idx % base
        nq = _vary_qa(datasets["qa"][src_i], variant)
        key = (nq["question"], nq["answer"])
        if key not in seen:
            seen.add(key)
            out["instruction"].append(_vary(datasets["instruction"][src_i], variant))
            out["qa"].append(nq)
            # rag는 instruction/qa보다 짧을 수 있으므로(원문 단위) 자체 길이로 순환한다.
            if rag_base:
                out["rag"].append(_vary_rag(datasets["rag"][src_i % rag_base], variant, len(out["rag"])))
        idx += 1
        if idx % base == 0:
            variant += 1
    return out


def _apply(text, variant):
    for a, b in _PARAPHRASE:
        text = text.replace(a, b)
    return f"{text} (변형 {variant})"


def _vary(d, v):
    d = copy.deepcopy(d)
    d["instruction"] = _apply(d["instruction"], v)
    # output도 함께 변형해 패딩 행이 원본과 같은 결과물을 반복하지 않게 한다.
    d["output"] = _apply(d["output"], v)
    d["_synthetic"] = True
    return d


def _vary_qa(d, v):
    d = copy.deepcopy(d)
    d["question"] = _apply(d["question"], v)
    # answer == output 이므로 동일하게 변형해 정합을 유지한다.
    d["answer"] = _apply(d["answer"], v)
    d["_synthetic"] = True
    return d


def _vary_rag(d, v, new_i):
    d = copy.deepcopy(d)
    d["id"] = f"DOC-S{new_i+1:04d}"
    d["_synthetic"] = True
    return d
