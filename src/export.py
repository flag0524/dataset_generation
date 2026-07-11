# STEP5/6/8 산출물 직렬화: CSV/JSON/Unsloth/리포트/메타데이터
import csv
import json
import os

from .config import config
from .schemas import CSV_COLUMNS


def write_csv(records: list, path: str):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        for r in records:
            row = dict(r)
            row["keyword"] = ", ".join(row.get("keyword", []))
            w.writerow({k: row.get(k, "") for k in CSV_COLUMNS})


def write_json(records: list, path: str):
    out = [{
        "id": r["id"],
        "domain": r["domain"],
        "category": r["category"],
        "instruction": r["instruction"],
        "input": r["input"],
        "output": r["output"],
        "metadata": {
            "source": r["source_document"],
            "keyword": r["keyword"],
            # 근거성 흔적: output이 원문(input)에 근거하는 정도와 플래그(감사 추적용).
            "grounding": r.get("grounding"),
            "grounded": r.get("grounded"),
            # 방법론 Entity 검증: 엔티티 근거성과 원문에 없는(환각 의심) 엔티티.
            "entity_grounding": r.get("entity_grounding"),
            "hallucinated_entities": r.get("hallucinated_entities", []),
            "source_span": r["input"],  # 근거 원문 구간(해당 청크)
            # 법안 최신성(발의안 오인 방지).
            "bill_number": r.get("bill_number"),
            "assembly_term": r.get("assembly_term"),
            "bill_status": r.get("bill_status"),
            "currency_notice": r.get("currency_notice"),
        },
    } for r in records]
    _dump(out, path)


def write_unsloth(unsloth: dict, out_dir: str, prefix: str = ""):
    # prefix가 있으면 도메인 업무명 접두를 붙인다(예: 공공행정_unsloth_alpaca.jsonl).
    head = f"{prefix}_" if prefix else ""
    for name, rows in unsloth.items():
        _dump_jsonl(rows, os.path.join(out_dir, f"{head}unsloth_{name}.jsonl"))


def write_metadata(record_count: int, path: str):
    _dump({
        "version": "1.0",
        "created_by": "AI Dataset Generator",
        "record_count": record_count,
    }, path)


def write_report(meta: dict, validation: dict, path: str, extraction_mode: str = None):
    lines = [
        f"# Dataset Report — {meta['document_name']}",
        "",
        f"- 도메인: {meta['domain']}",
        f"- 목적: {meta['purpose']}",
        f"- 키워드: {', '.join(meta['keywords'])}",
        f"- 지식 추출 모드: {extraction_mode or 'heuristic'}",
        "",
        "## 검증 결과",
        f"- 데이터셋 버전: 1.0",
        f"- 품질 점수: {validation['quality_score']}",
        f"- 상태: {validation['status']}",
        f"- 레코드 수: {validation['row_count']}",
        f"- 중복 제거: {validation['duplicates_removed']}",
        f"- 품질 필터링: {validation['quality_filtered']}",
        f"- 포맷 일관성: {validation['format_consistent']}",
        f"- 크기 기준 충족: {validation['size_ok']}",
        f"- category 분포: {', '.join(f'{k} {v}' for k, v in validation.get('category_dist', {}).items()) or '-'}",
        f"- 평균 근거성(어휘): {validation.get('mean_grounding', 0)}",
        f"- 저근거 레코드: {validation.get('low_grounding', 0)}건",
    ]
    # 방법론(DocumentAI 검증방법론 §공공기관 권장 기준) 8개 항목 대비 판정.
    # 기준값은 config(단일 진입점)에서 읽고, 각 항목을 충족(✅)/미달(❌)/N/A로 표시한다.
    # 측정 불가 항목(의미유사도 OFF, OCR 입력단계)은 N/A로 둔다.
    def _mark(ok):
        return "N/A" if ok is None else ("✅ 충족" if ok else "❌ 미달")

    eg = validation.get("entity_grounding")
    ms = validation.get("mean_semantic")
    hr = validation.get("hallucination_rate", 0)
    dr = validation.get("duplicate_rate", 0)
    score = validation["quality_score"]
    rows = [
        ("최종 품질", f"{config.std_quality}점 이상(A)", f"{score}점 ({validation.get('grade', '-')})",
         score >= config.std_quality),
        ("엔티티 근거성(Grounding)", f"{config.std_grounding} 이상",
         f"{eg}" if eg is not None else "N/A(엔티티 없음)", None if eg is None else eg >= config.std_grounding),
        ("의미 유사도", f"{config.std_semantic} 이상",
         f"{ms}" if ms is not None else "N/A(SEMANTIC_ENABLED=1로 측정)", None if ms is None else ms >= config.std_semantic),
        ("환각 의심율", f"{config.std_hallucination_max}% 이하", f"{hr}%", hr <= config.std_hallucination_max),
        ("중복률", f"{config.std_duplicate_max}% 이하", f"{dr}%", dr <= config.std_duplicate_max),
        ("메타데이터 완전성", "100%", "100%" if validation.get("metadata_complete") else "미완",
         bool(validation.get("metadata_complete"))),
        ("OCR 정확도", f"{config.std_ocr}% 이상", "입력 단계 기준(런타임 미측정)", None),
    ]
    met = sum(1 for *_, ok in rows if ok is True)
    checkable = sum(1 for *_, ok in rows if ok is not None)
    lines += [
        "",
        "## 방법론 검증 (공공기관 권장 기준)",
        f"- 기준 충족: {met}/{checkable} (측정 가능 항목 기준; N/A는 제외)",
        "",
        "| 항목 | 기준 | 측정값 | 판정 |",
        "| --- | --- | --- | --- |",
    ]
    lines += [f"| {name} | {std} | {val} | {_mark(ok)} |" for name, std, val, ok in rows]
    lines += [
        "",
        f"- 초단답(30자 미만): {validation.get('short_answer_count', 0)}건 (검수 권장)",
        f"- 부정문 의미반전 위험: {validation.get('negation_mismatch_count', 0)}건 "
        "(원문 부정어가 답변에서 사라짐 — 검수 우선)",
    ]
    _rg = validation.get("ragas")
    if _rg:
        lines.append(
            f"- RAGAS(LLM 심판, n={_rg['sampled']}): "
            f"faithfulness {_rg['faithfulness']} · answer_relevancy {_rg['answer_relevancy']}"
        )
    # 법안 최신성(보고서 §4) — 발의안을 현행법으로 오인하지 않도록 명시.
    if meta.get("is_bill"):
        lines += [
            "",
            "## 법안 최신성 (주의)",
            f"- 의안번호: {meta.get('bill_number') or '미상'} / 발의일: {meta.get('propose_date') or '미상'} / {meta.get('assembly_term') or '대수 미상'}",
            f"- 처리 상태: {meta.get('bill_status')} (의안정보시스템 likms.assembly.go.kr에서 확인 필요)",
            f"- {meta.get('currency_notice')}",
        ]
    if validation["issues"]:
        lines += ["", "## 이슈"] + [f"- {i}" for i in validation["issues"]]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def append_history(record: dict, path: str):
    # 실행 1건의 요약을 JSONL로 누적한다(대시보드 이력 소스). 산출물과 달리
    # 덮어쓰지 않고 append 한다.
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _dump(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _dump_jsonl(rows, path):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
