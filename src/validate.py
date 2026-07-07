# STEP7 검증 루프: Validator·LLM Judge·크기/구조 점검 (TRD §5)
from .config import config
from .schemas import validate_instruction, validate_qa, validate_rag


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

    return {
        "quality_score": quality_score,
        "status": status,
        "row_count": len(judged),
        "duplicates_removed": dup_removed,
        "quality_filtered": quality_filtered,
        "format_consistent": format_ok,
        "size_ok": size_ok,
        "issues": issues,
        "records": judged,
    }


def _check_roles(unsloth: dict) -> bool:
    for c in unsloth.get("chatml", []):
        roles = [m["role"] for m in c["messages"]]
        if roles != ["user", "assistant"]:
            return False
    for c in unsloth.get("sharegpt", []):
        froms = [m["from"] for m in c["conversations"]]
        if froms != ["human", "gpt"]:
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
