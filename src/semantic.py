# 문장 임베딩 기반 의미 유사도(방법론 '의미 보존 검증', 선택적).
# transformers+torch와 임베딩 모델이 있으면 계산하고, 없으면 None을 돌려 조용히 스킵한다.
# 망분리 환경에서는 SEMANTIC_MODEL 모델을 오프라인 반입해야 활성화된다.
import os

_MODEL = None
_LOAD_FAILED = False


def _get_model():
    # 임베딩 모델을 1회 로드해 캐시한다. 의존성·모델 부재 시 이후 호출은 즉시 None.
    global _MODEL, _LOAD_FAILED
    if _MODEL is not None or _LOAD_FAILED:
        return _MODEL
    try:
        import torch
        from transformers import AutoModel, AutoTokenizer
        name = os.getenv("SEMANTIC_MODEL",
                         "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
        tok = AutoTokenizer.from_pretrained(name)
        mdl = AutoModel.from_pretrained(name)
        mdl.eval()
        _MODEL = (tok, mdl, torch)
    except Exception:
        _LOAD_FAILED = True
    return _MODEL


def semantic_similarity(a: str, b: str):
    # 두 문장의 코사인 유사도(-1~1). 모델 미가용 시 None.
    m = _get_model()
    if m is None:
        return None
    tok, mdl, torch = m

    def emb(t):
        x = tok(t or "", return_tensors="pt", truncation=True, max_length=256, padding=True)
        with torch.no_grad():
            o = mdl(**x)
        mask = x["attention_mask"].unsqueeze(-1).float()
        v = (o.last_hidden_state * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
        return torch.nn.functional.normalize(v, dim=1)

    return round(float((emb(a) * emb(b)).sum()), 3)
