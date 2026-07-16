# 손으로 교정한 정답셋(gold)을 절대 기준으로 삼아 새 생성 output의 의미 유사도를 재는 모듈.
#
# 배경: 기존 의미 유사도는 output↔input(같은 원문)을 비교했다. 그런데 output은 재진술이고
# input은 원문 발췌라 애초에 다른 글이라, 0.7~0.8이 나와도 좋은지 나쁜지 판단할 절대 기준이
# 없었다. gold는 "이 원문에 대한 이상적 정답 output"(사람 교정본)이므로, 유사도(생성, gold)로
# 절대 합격선을 세울 수 있다. 완전 자동 생성이 아니라 손으로 다듬은 output/건설국토_dataset.json을
# gold로 재활용한다(별도 제작 불필요).
#
# 매칭 원리: 새 생성 레코드의 input(소스 세그먼트)이 gold의 input과 겹칠 때만 비교한다
# (같은 원천 문서를 재생성할 때 소스가 일치). 매칭은 토큰 Jaccard로 싸게(모델 없이) 하고,
# 임베딩은 매칭된 output 쌍에만 돌려 비용을 줄인다. 소스가 안 겹치는 도메인은 매칭 0으로
# 정직하게 처리한다(무관한 gold와 억지 비교하지 않음).
import json
import re

_WS = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _WS.sub(" ", (s or "")).strip()


def _tokens(s: str) -> set:
    return set(_norm(s).split())


def load_gold(path: str) -> list:
    """gold JSON에서 (input, output) 쌍을 읽는다. 파일·형식 오류 시 빈 리스트."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    pairs = []
    for r in data:
        if not isinstance(r, dict):
            continue
        inp = r.get("input") or (r.get("metadata") or {}).get("source_span") or ""
        out = r.get("output") or r.get("answer") or ""
        if inp and out:
            pairs.append({"input": _norm(inp), "output": out})
    return pairs


def _best_gold(inp: str, gold: list, min_overlap: float):
    """생성 레코드의 input과 소스가 가장 겹치는 gold를 토큰 Jaccard로 찾는다.
    겹침이 임계값 미만이면 None(같은 원천이 아님)."""
    it = _tokens(inp)
    if not it:
        return None
    best, best_j = None, 0.0
    for g in gold:
        gt = _tokens(g["input"])
        if not gt:
            continue
        j = len(it & gt) / len(it | gt)
        if j > best_j:
            best, best_j = g, j
    return best if best_j >= min_overlap else None


def score_against_gold(records: list, gold: list, semantic_fn, min_overlap: float = 0.6) -> dict:
    """각 생성 output을, 소스가 일치하는 gold output과 의미 비교한다.

    반환: {"matched": n, "mean_gold_semantic": f 또는 None}
      matched — gold와 소스가 겹쳐 실제로 비교한 레코드 수
      mean_gold_semantic — 그 레코드들의 유사도(생성output, gold output) 평균
    """
    if not gold or not records:
        return {"matched": 0, "mean_gold_semantic": None}
    sims = []
    for r in records:
        g = _best_gold(r.get("input", ""), gold, min_overlap)
        if g is None:
            continue
        s = semantic_fn(r.get("output", ""), g["output"])
        if s is not None:
            sims.append(s)
    if not sims:
        return {"matched": 0, "mean_gold_semantic": None}
    return {"matched": len(sims), "mean_gold_semantic": round(sum(sims) / len(sims), 3)}
