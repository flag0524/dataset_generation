# STEP4 보조: 분량 부족 시 합성 데이터로 증강 (PRD FR-11, Unsloth 가이드 §2-4)
import copy

_PARAPHRASE = [
    ("설명하라", "기술하라"),
    ("에 대해", "에 관하여"),
    ("관점에서", "입장에서"),
]


def augment(datasets: dict, target: int) -> dict:
    # instruction/qa/rag를 동일 개수로 유지하며 target까지 증강
    base = len(datasets["qa"])
    if base == 0 or base >= target:
        return datasets
    out = {k: list(v) for k, v in datasets.items()}
    idx = 0
    while len(out["qa"]) < target:
        src_i = idx % base
        variant = idx // base + 1
        out["instruction"].append(_vary(datasets["instruction"][src_i], variant))
        out["qa"].append(_vary_qa(datasets["qa"][src_i], variant))
        out["rag"].append(_vary_rag(datasets["rag"][src_i], variant, len(out["rag"])))
        idx += 1
    return out


def _apply(text, variant):
    for a, b in _PARAPHRASE:
        text = text.replace(a, b)
    return f"{text} (변형 {variant})"


def _vary(d, v):
    d = copy.deepcopy(d)
    d["instruction"] = _apply(d["instruction"], v)
    d["_synthetic"] = True
    return d


def _vary_qa(d, v):
    d = copy.deepcopy(d)
    d["question"] = _apply(d["question"], v)
    d["_synthetic"] = True
    return d


def _vary_rag(d, v, new_i):
    d = copy.deepcopy(d)
    d["id"] = f"DOC-S{new_i+1:04d}"
    d["_synthetic"] = True
    return d
