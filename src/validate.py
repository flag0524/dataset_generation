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


def run_validation(datasets: dict, unsloth: dict, records: list) -> dict:
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

    return {
        "quality_score": quality_score,
        "status": status,
        "row_count": len(judged),
        "duplicates_removed": dup_removed,
        "quality_filtered": quality_filtered,
        "format_consistent": format_ok,
        "size_ok": size_ok,
        "mean_grounding": mean_grounding,
        "low_grounding": low_grounding,
        "issues": issues,
        "records": judged,
    }


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
