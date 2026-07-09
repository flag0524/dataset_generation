# 8단계 데이터셋 생성 파이프라인의 각 STEP 구현 (TRD §1 아키텍처)
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from .config import config
from .llm import LLMClient

# STEP2 도메인 → 전문가 역할 라우팅 테이블 (TRD §6).
# 법안·보고서는 여러 분야 용어가 섞이므로, 분야별 키워드를 풍부하게 두어 문서의
# 주제 도메인(외교·국방·건설 등)으로 라우팅한다. '법률'은 특정 주제색이 옅은
# 일반 법률문서용 폴백에 가깝게 둔다.
EXPERT_ROUTING = {
    "공공행정": "지방행정 전문가",
    "법률": "법률 분석 전문가",
    "금융": "금융 업무 전문가",
    "외교": "외교·통일 전문가",
    "국방": "국방·안보 전문가",
    "교육": "교육정책 전문가",
    "환경": "환경정책 전문가",
    "노동": "노동·고용 전문가",
    "보건의료": "보건의료 전문가",
    "산업경제": "산업·경제 전문가",
    "건설국토": "건설·국토 전문가",
    "농림수산": "농림·수산 전문가",
    "일반": "도메인 전문가",
}

DOMAIN_KEYWORDS = {
    "공공행정": ["행정", "지자체", "지방자치", "민원", "조례", "공공", "행정안전", "주민", "자치단체", "공무원"],
    "법률": ["법률", "법령", "판례", "소송", "개정", "법률안", "발의", "벌칙", "과태료", "시행령", "위반"],
    "금융": ["금융", "대출", "예금", "투자", "이자", "계좌", "자본금", "적립금", "재무", "회계", "출자"],
    "외교": ["외교", "통일", "조약", "협정", "국제", "대사", "영사", "재외국민", "수교", "외교부", "남북"],
    "국방": ["국방", "병역", "안보", "군인", "방위", "군사", "병력", "국군", "장병", "예비군", "부대"],
    "교육": ["교육", "학교", "학생", "교원", "대학", "교사", "학습", "교육부", "입시", "학위", "유치원"],
    "환경": ["환경", "오염", "폐기물", "배출", "생태", "탄소", "기후", "재활용", "환경부", "온실가스", "대기"],
    "노동": ["노동", "근로", "임금", "고용", "해고", "노조", "산업재해", "근로자", "최저임금", "일자리", "퇴직"],
    "보건의료": ["보건", "의료", "질병", "병원", "환자", "의약품", "건강", "방역", "진료", "감염병", "복지"],
    "산업경제": ["산업", "경제", "기업", "무역", "수출", "제조", "중소기업", "상공", "공정거래", "소상공인"],
    "건설국토": ["건설", "국토", "도로", "주택", "공사", "시공", "건축", "부동산", "도시", "하수급", "공제조합", "수급인"],
    "농림수산": ["농업", "농림", "수산", "어업", "축산", "임업", "농민", "농촌", "수산물", "어민", "농산물"],
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
# 신구조문 대비표 파편 — '(현행과 같음)', '<신 설>', '<삭 제>' 같은 조각은 문맥이 없어
# 환각성 output을 만든다(보고서 2-4). 이런 마커가 있으면 저품질 청크로 본다.
_AMENDMENT_NOISE = re.compile(r"현행과\s*같음|<\s*신\s*설\s*>|<\s*삭\s*제\s*>|신구조문")


def _is_noise(s: str) -> bool:
    # 목차 점선·페이지번호·신구조문 대비표 파편 등 학습 가치 없는 청크인지 판별한다.
    if any(p.match(s) for p in _NOISE_PATTERNS):
        return True
    if _AMENDMENT_NOISE.search(s):
        return True
    # 점선(dot leader)이 대부분을 차지하는 목차 항목 (예: "제안경위 ·········· 3")
    dots = sum(s.count(c) for c in ".·․…‥∙⋯")
    return dots >= 6 and dots >= len(s) * 0.3


def _segments(text: str):
    # 문서를 의미 있는 문장 청크로 분해한다. PDF 추출 텍스트는 문장 중간에서 줄바꿈되므로,
    # 먼저 문단 내 줄바꿈을 공백으로 이어 붙여 문장이 중간에서 잘리지 않게 한 뒤,
    # 문장 경계(마침표·물음표 등)로만 분할한다. 목차·대비표 파편·초단문은 걸러낸다.
    parts = re.split(r"\n\s*\n", text)
    segs = []
    for p in parts:
        # 문단 내 단일 줄바꿈은 문장 연속으로 보고 공백으로 결합(중간 잘림 방지).
        joined = re.sub(r"\s*\n\s*", " ", p).strip()
        if not joined:
            continue
        for s in re.split(r"(?<=[.!?。])\s+", joined):
            s = s.strip(" -*#\t·")
            if len(s) >= config.min_seg_len and not _is_noise(s):
                segs.append(s)
    return segs


# ---------- STEP 1. 문서 분석 ----------
def analyze(text: str, document_name: str, llm: LLMClient) -> dict:
    domain = _classify_domain(text, llm)
    keywords = _top_keywords(text)
    purpose = _segments(text)[0] if _segments(text) else ""
    return {
        "document_name": document_name,
        "domain": domain,
        "purpose": purpose[:120],
        "keywords": keywords,
    }


def _classify_domain(text: str, llm: LLMClient = None) -> str:
    # 정밀 분류: LLM이 가용하면 문맥으로 주제 도메인을 고른다(흔한 단어 지배 문제 회피).
    # 미가용(mock/테스트)이거나 목록 밖 응답이면 키워드 카운트로 폴백한다.
    if llm is not None and llm.available():
        d = _llm_classify_domain(text, llm)
        if d in DOMAIN_KEYWORDS or d == "일반":
            return d
    return _keyword_classify_domain(text)


def _llm_classify_domain(text: str, llm: LLMClient) -> str:
    domains = list(EXPERT_ROUTING)  # '일반' 포함
    data = llm.generate_json(
        f"다음 문서의 주제 도메인을 아래 목록에서 정확히 하나만 골라라: {', '.join(domains)}.\n"
        "위원회/발의 형식이 아니라 문서가 실제로 다루는 주제로 판단하라"
        "(예: 통일·남북·조약 → 외교, 병역·군 → 국방, 건설·공사 → 건설국토).\n"
        '반드시 JSON만: {"domain":"<목록 중 하나>"}\n\n'
        f"문서 앞부분:\n{text[:2000]}",
        system="너는 한국어 공공문서 도메인 분류기다. 반드시 주어진 목록 중 하나만 고른다.",
    )
    return str((data or {}).get("domain", "")).strip()


def _keyword_classify_domain(text: str) -> str:
    scores = {d: sum(text.count(k) for k in kws) for d, kws in DOMAIN_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "일반"


# 키워드에서 제외할 한국어 불용어(조사·접속사·의존명사·형식어). 형태소 분석기 없이
# (망분리) 빈도 상위에 올라오는 조사/접속사류를 제거해 의미 키워드만 남긴다.
# 후행 조사 분리(_strip_josa)로도 못 거르는 짧은 결합형·명사화어는 여기에 직접 넣는다.
_STOPWORDS = {
    "또는", "관한", "관하여", "대한", "대하여", "위한", "위하여", "그리고", "그러나", "따라",
    "따른", "따라서", "이하", "이상", "경우", "때문", "통해", "통하여", "및", "등", "등의",
    "기준", "관련", "해당", "각각", "모든", "어느", "다음", "같은", "있는", "없는", "하는",
    "되는", "이러한", "그러한", "우리", "본", "제", "그", "이", "저", "것", "수", "바",
    "한다", "된다", "했다", "하고", "하여", "하며", "된", "하는데", "이다", "있다", "없다",
    "것으로", "것을", "등을", "등이", "있음", "없음", "함으로", "됨", "임", "대해", "위해",
    "필요한", "필요", "관련된",
}

# 법령 인용 스캐폴딩(제N조·제N조의M·제N항/호/목 등). 중간 숫자가 한글 토큰을 쪼개
# '조의'(제57조의3)·'조제'(제96조제5호) 같은 조문 조각을 만드는 것을 원천 차단한다.
_CITATION_PATTERNS = [
    re.compile(r"제\s*\d+\s*조(\s*의\s*\d+)?"),  # 제12조, 제12조의2
    re.compile(r"제\s*\d+\s*[항호목관장절]"),      # 제3항, 제1호
]

# 토큰 꼬리에서 떼어낼 조사(긴 것부터 시도). 남는 어간이 2자 이상일 때만 분리해
# '정의'→'정' 같은 오절단을 막는다. 결과적으로 '공제조합의'→'공제조합'으로 병합된다.
_JOSA = ("으로서", "으로써", "으로", "이라", "에서", "에게", "에도", "라도",
         "의", "을", "를", "이", "가", "은", "는", "에", "로", "과", "와", "도", "만")


def _strip_josa(w: str) -> str:
    for j in _JOSA:  # 긴 조사부터 매칭(_JOSA는 길이 내림차순 정렬 가정)
        if w.endswith(j) and len(w) - len(j) >= 2:
            return w[: -len(j)]
    return w


def _top_keywords(text: str, n: int = 10):
    # 2자 이상 한글/영문 토큰 빈도 상위 n개. 먼저 법령 인용 스캐폴딩을 제거하고,
    # 후행 조사를 떼고 불용어를 제외해 명사+조사 결합형·조문 조각·조사류를 정리한다.
    for pat in _CITATION_PATTERNS:
        text = pat.sub(" ", text)
    words = re.findall(r"[가-힣A-Za-z]{2,}", text)
    freq = {}
    for w in words:
        if w in _STOPWORDS:  # 원형이 결합형 불용어('것으로','등을')면 분리 전에 제외
            continue
        w = _strip_josa(w)
        if len(w) < 2 or w in _STOPWORDS:
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

# 앵글별 LLM 질문 생성 실패 시 쓰는 일반 질문(원문 절단이 아니라 안전한 고정 문구).
_GENERIC_Q = {
    "explain": "이 내용을 업무 담당자가 이해하도록 설명해 주세요.",
    "summarize": "이 내용의 핵심을 요약하면 무엇인가요?",
    "rule": "이 내용에 적용되는 업무 처리 기준은 무엇인가요?",
    "terms": "이 내용의 핵심 용어와 의미는 무엇인가요?",
}


def _derive_outputs(seg: str, meta: dict, expert: str, llm: LLMClient, deadline=None) -> dict:
    # 한 세그먼트에서 앵글별 (질문 q, 답변 a)과 청크 키워드를 LLM 1회 호출로 얻는다.
    # 반환: {"angles": {kind: {"q":.., "a":..}}, "keywords": [..]} — a가 15자 이상인
    # 앵글만 채택. 질문·키워드도 LLM이 생성하므로 원문 절단·문서단위 복사 문제가 없다.
    # - 예산 소진/빈 응답: 폴백 없이 빈 결과(청크 드롭).
    # - LLM 미가용(mock/테스트): 결정론적 구조 출력으로 end-to-end 보장(학습용 아님).
    kinds = [k for _, k in _TASKS]
    if not llm.available():
        return _mock_derive(seg, meta, expert)
    use_llm, timeout = _budget_timeout(deadline)
    if not use_llm:
        return {}
    data = llm.generate_json(
        "다음 내용을 바탕으로 네 가지 과제의 질문(q)과 답변(a)을 만들어라.\n"
        "답변(a)은 원문을 통째로 베끼지는 말되, 원문의 핵심 용어·수치·금액·기간·조문 번호\n"
        "(예: 제57조의3)·기관명은 반드시 그대로 유지하라(사실 근거 보존). 문장 표현만 새로 쓴다.\n"
        "질문(q)은 원문을 자르지 말고 완결된 자연스러운 한국어 의문문으로 작성하라.\n"
        "- explain: 업무 담당자가 이해하도록 2~3문장 설명\n"
        "- summarize: 한 문장 요약\n"
        "- rule: '조건 → 처리' 형태의 업무 기준 한 문장\n"
        "- terms: 핵심 용어 2~3개와 각 의미\n"
        "- keywords: 이 내용의 핵심 키워드 2~3개(명사) 배열\n"
        '반드시 JSON만 출력하라: {"explain":{"q":"","a":""},"summarize":{"q":"","a":""},'
        '"rule":{"q":"","a":""},"terms":{"q":"","a":""},"keywords":["",""]}\n\n'
        f"내용:\n{seg}",
        system=f"너는 {expert}다. 한국어로 간결·정확하게 답하되 원문의 사실(용어·수치·조문)을 보존하라.",
        timeout=timeout,
    )
    if not isinstance(data, dict):
        return {}
    angles = {}
    for k in kinds:
        item = data.get(k) or {}
        if not isinstance(item, dict):
            continue
        a = str(item.get("a", "")).strip()
        if len(a) < 15:  # 유효 답변이 있는 앵글만 채택
            continue
        q = str(item.get("q", "")).strip() or _GENERIC_Q[k]
        angles[k] = {"q": q, "a": a}
    kws = [str(w).strip() for w in (data.get("keywords") or []) if str(w).strip()]
    return {"angles": angles, "keywords": kws[:3]}


def _mock_derive(seg: str, meta: dict, expert: str) -> dict:
    # LLM 미가용(mock/테스트) 전용 결정론적 출력. 실제 LLM 경로에서는 호출되지 않으며
    # 학습용 데이터가 아니다(파이프라인 end-to-end 구동·구조 검증 목적).
    kw = ", ".join(meta["keywords"][:3]) or "핵심 사항"
    a = {
        "explain": f"[mock] {expert}의 관점에서 보면 이 내용은 다음을 뜻한다 — {seg}.",
        "summarize": f"[mock] 요약하면, 본문은 '{seg[:40]}' 등을 다루는 내용이다.",
        "rule": f"[mock] 처리 기준: '{seg[:40]}' 상황에서 {expert}가 정해진 절차를 적용한다.",
        "terms": f"[mock] 핵심 용어는 {kw}이며, 본문은 이를 중심으로 기술되어 있다.",
    }
    angles = {k: {"q": _GENERIC_Q[k], "a": v} for k, v in a.items()}
    return {"angles": angles, "keywords": _top_keywords(seg, n=3)}


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
        res = seg_outputs[i] or {}
        angles = res.get("angles", {})
        # 청크 키워드는 레코드별로 부여한다(문서 단위 복사 지양). 없으면 문서 키워드로 폴백.
        chunk_kw = res.get("keywords") or meta["keywords"][:3]
        # RAG 패시지는 원문 자체(생성물 아님)라 항상 유지한다.
        rags.append({
            "id": f"DOC-{i+1:04d}",
            "title": seg[:30],
            "content": seg,
            "metadata": {"keyword": chunk_kw},
        })
        # instruction/QA는 LLM이 실제로 만든 앵글만 레코드로 만든다(못 만든 앵글은 드롭).
        # 질문(q)도 LLM 생성이라 원문 절단 문제가 없다.
        for tmpl, kind in _TASKS:
            item = angles.get(kind)
            if not item:
                continue
            instructions.append({
                "instruction": tmpl.format(expert=expert),
                "input": seg,
                "output": item["a"],
                "keyword": chunk_kw,
            })
            qas.append({"question": item["q"], "answer": item["a"], "source": src, "keyword": chunk_kw})
    return {"instruction": instructions, "qa": qas, "rag": rags}


# ---------- STEP 4.5 Unsloth 포맷 변환 ----------
def to_unsloth_formats(datasets: dict) -> dict:
    raw = [{"text": d["output"]} for d in datasets["instruction"]]
    # Unsloth/HuggingFace 표준 alpaca 매핑은 소문자 키를 기대한다(대문자면 KeyError 위험).
    alpaca = [
        {"instruction": d["instruction"], "input": d["input"], "output": d["output"]}
        for d in datasets["instruction"]
    ]
    # 대화형 포맷은 instruction 삼중항을 3턴으로 옮긴다(보고서 2-2): system=지시,
    # user=원문(input), assistant=출력. user 턴에 원문 근거가 실려 문서기반 학습이 된다.
    sharegpt = [
        {"conversations": [
            {"from": "system", "value": d["instruction"]},
            {"from": "human", "value": d["input"]},
            {"from": "gpt", "value": d["output"]},
        ]}
        for d in datasets["instruction"]
    ]
    chatml = [
        {"messages": [
            {"role": "system", "content": d["instruction"]},
            {"role": "user", "content": d["input"]},
            {"role": "assistant", "content": d["output"]},
        ]}
        for d in datasets["instruction"]
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
            "keyword": inst.get("keyword", meta["keywords"][:3]),  # 레코드(청크) 단위 키워드
            "created_date": today,
        })
    return records
