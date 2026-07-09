# STEP5/6/8 산출물 직렬화: CSV/JSON/Unsloth/리포트/메타데이터
import csv
import json
import os

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
            "source_span": r["input"],  # 근거 원문 구간(해당 청크)
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
        f"- 평균 근거성: {validation.get('mean_grounding', 0)}",
        f"- 저근거 레코드: {validation.get('low_grounding', 0)}건",
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
