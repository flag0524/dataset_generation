# STEP4 보조: 분량 부족 시 합성 데이터로 증강 (PRD FR-11, Unsloth 가이드 §2-4)
import copy

# 합성 행은 원본 고유 행의 최대 이 배수까지만 만든다. 작은 문서를 min_rows까지
# 무리하게 부풀려 같은 내용이 수십 번 반복되는 것을 막는다(부족하면 그 선에서 멈춤).
MAX_SYNTHETIC_MULT = 5

_PARAPHRASE = [
    ("설명하라", "기술하라"),
    ("에 대해", "에 관하여"),
    ("관점에서", "입장에서"),
]

# variant별 서로 다른 재진술 틀. '(변형 N)' 번호 반복 대신 표현 자체를 바꿔 다양성을 높인다.
_VARIANT_STYLES = [
    "다시 말하면, {t}",
    "{t} (핵심 위주로 정리)",
    "바꿔 표현하면 {t}",
    "{t} (요점 재정리)",
    "정리하자면, {t}",
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
    # instruction/qa/rag를 동일 개수로 유지하며 target까지 증강한다.
    # 합성 행은 원본의 MAX_SYNTHETIC_MULT 배까지만 만들어, 작은 문서를 무리하게
    # 부풀리지 않는다(부족하면 그 선에서 멈추므로 행 수는 적어도 중복이 크게 준다).
    # 충돌(question, answer 동일)하는 변형은 건너뛰며, 진전이 없으면 종료한다.
    base = len(datasets["qa"])
    rag_base = len(datasets["rag"])
    if base == 0 or base >= target:
        return datasets
    target = min(target, base * MAX_SYNTHETIC_MULT)
    out = {k: list(v) for k, v in datasets.items()}
    seen = {(q["question"], q["answer"]) for q in out["qa"]}
    idx, variant, stale = 0, 1, 0
    while len(out["qa"]) < target and stale < base * len(_VARIANT_STYLES) * 2:
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
            stale = 0
        else:
            stale += 1
        idx += 1
        if idx % base == 0:
            variant += 1
    return out


def _apply(text, variant):
    # variant마다 다른 재진술 틀을 적용해 표현을 다양화한다(번호만 붙는 반복 제거).
    for a, b in _PARAPHRASE:
        text = text.replace(a, b)
    style = _VARIANT_STYLES[(variant - 1) % len(_VARIANT_STYLES)]
    return style.format(t=text)


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
