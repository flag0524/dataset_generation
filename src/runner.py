# 8단계 파이프라인을 순차 오케스트레이션하는 진입점 (TRD §1)
import os
import re
import time

from . import pipeline, export, validate
from .config import config
from .llm import LLMClient
from .loaders import load_document


def _domain_prefix(domain: str) -> str:
    # 산출물 파일명 접두를 도메인 업무명으로 만든다(예: 공공행정 → "공공행정").
    # 파일시스템에 안전하도록 공백·경로문자만 _로 치환한다.
    prefix = re.sub(r"[\\/:*?\"<>|\s]+", "_", (domain or "").strip())
    return prefix or "domain"


# 진행률 이벤트 단계 라벨 (UI 진행 표시용)
_STAGES = [
    "문서 로딩", "문서 분석", "전문가 라우팅", "지식 추출",
    "데이터셋 생성", "포맷 변환", "품질 검증", "산출물 저장",
]


def run(path: str, out_dir: str = None, on_progress=None, time_budget: float = None) -> dict:
    # time_budget(초): 양수면 STEP3~4 LLM 작업에 벽시계 예산을 걸어 초과 청크를 드롭한다
    # (웹 '빠른 미리보기' 전용, 산출물은 미완성·학습용 아님). None이면 config 값을 쓰며
    # 기본 0=무제한이라 데이터셋 생성은 모든 청크를 실제 LLM으로 만든다.
    out_dir = out_dir or config.output_dir
    os.makedirs(out_dir, exist_ok=True)
    llm = LLMClient()
    document_name = os.path.basename(path)

    budget = time_budget if time_budget is not None else config.llm_time_budget
    deadline = time.monotonic() + budget if (budget and budget > 0 and llm.available()) else None

    total = len(_STAGES)

    def _emit(i):
        # on_progress(event)로 단계 진행을 전달. 미지정 시 무동작(테스트·CLI 안전).
        if on_progress:
            on_progress({"step": i, "total": total, "stage": _STAGES[i - 1]})

    # STEP1~2
    _emit(1)
    text = load_document(path)
    _emit(2)
    meta = pipeline.analyze(text, document_name, llm)
    _emit(3)
    expert = pipeline.route_expert(meta["domain"])

    # STEP3
    _emit(4)
    extracted = pipeline.extract_knowledge(text, meta, llm, deadline=deadline)

    # STEP4 — 실제 LLM으로 생성한 청크만 남는다(합성 증강 없음: 품질 우선).
    _emit(5)
    datasets = pipeline.generate_datasets(text, meta, extracted, llm, deadline=deadline)

    # STEP4.5 / STEP5·6 / STEP7 — 검증으로 중복·저품질을 제거해 최종 레코드를 만든다.
    _emit(6)
    records = pipeline.to_records(meta, datasets)
    _emit(7)
    validation = validate.run_validation(datasets, pipeline.to_unsloth_formats(datasets), records)
    final_records = validation["records"]

    # Unsloth JSONL은 정제 후 최종 레코드에서 생성해 JSON/CSV와 건수·내용을 일치시킨다
    # (과거엔 정제 전 datasets에서 생성돼 미정제본이 학습에 쓰이는 문제가 있었다).
    clean_datasets = {
        "instruction": [{"instruction": r["instruction"], "input": r["input"],
                         "output": r["output"], "keyword": r["keyword"]}
                        for r in final_records],
        "qa": [{"question": r["question"], "answer": r["answer"],
                "source": r["source_document"], "keyword": r["keyword"]}
               for r in final_records],
        "rag": datasets["rag"],
    }
    unsloth = pipeline.to_unsloth_formats(clean_datasets)

    # STEP5/6/8 산출 — 파일명은 도메인 업무명 접두를 따른다(예: 공공행정_dataset.csv).
    _emit(8)
    prefix = _domain_prefix(meta["domain"])
    artifacts = {
        "csv": f"{prefix}_dataset.csv",
        "json": f"{prefix}_dataset.json",
        "metadata": f"{prefix}_dataset_metadata.json",
        "report": f"{prefix}_dataset_report.md",
        "unsloth_raw": f"{prefix}_unsloth_raw.jsonl",
        "unsloth_alpaca": f"{prefix}_unsloth_alpaca.jsonl",
        "unsloth_sharegpt": f"{prefix}_unsloth_sharegpt.jsonl",
        "unsloth_chatml": f"{prefix}_unsloth_chatml.jsonl",
    }
    export.write_csv(final_records, os.path.join(out_dir, artifacts["csv"]))
    export.write_json(final_records, os.path.join(out_dir, artifacts["json"]))
    export.write_unsloth(unsloth, out_dir, prefix=prefix)
    export.write_metadata(len(final_records), os.path.join(out_dir, artifacts["metadata"]))
    export.write_report(meta, validation, os.path.join(out_dir, artifacts["report"]),
                        extraction_mode=extracted.get("extraction_mode"))

    # 대시보드 이력: 실행 1건 요약을 누적 (산출물과 달리 append)
    from datetime import datetime
    export.append_history({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "document_name": meta["document_name"],
        "domain": meta["domain"],
        "expert": expert,
        "row_count": validation["row_count"],
        "quality_score": validation["quality_score"],
        "status": validation["status"],
        "extraction_mode": extracted.get("extraction_mode"),
        "llm_mode": "ollama" if llm.available() else "mock",
    }, os.path.join(out_dir, "history.jsonl"))

    return {
        "meta": meta,
        "expert": expert,
        "extraction_mode": extracted.get("extraction_mode"),
        "knowledge": extracted["knowledge"],
        "rules": extracted["rules"],
        "datasets": datasets,
        "unsloth": unsloth,
        "validation": validation,
        "output_dir": out_dir,
        "artifacts": artifacts,
        "llm_mode": "ollama" if llm.available() else "mock",
    }


def run_many(paths: list, out_dir: str = None, name: str = "법률_통합",
             on_progress=None, time_budget: float = None) -> dict:
    # 여러 문서를 하나의 데이터셋으로 통합 생성한다(P1-4 다양성). 문서별로 STEP1~4를
    # 돌려 레코드를 모은 뒤 전체를 재ID·중복제거·근거성 검증하고 단일 산출물로 낸다.
    # 소스가 여럿이라 특정 법안 표현 과적합 위험이 준다.
    out_dir = out_dir or config.output_dir
    os.makedirs(out_dir, exist_ok=True)
    llm = LLMClient()
    budget = time_budget if time_budget is not None else config.llm_time_budget

    all_records, all_rag, sources, all_keywords = [], [], [], []
    for n, path in enumerate(paths, 1):
        if on_progress:
            on_progress({"step": n, "total": len(paths), "stage": f"문서 {n}/{len(paths)} 처리"})
        text = load_document(path)
        meta = pipeline.analyze(text, os.path.basename(path), llm)
        deadline = time.monotonic() + budget if (budget and budget > 0 and llm.available()) else None
        extracted = pipeline.extract_knowledge(text, meta, llm, deadline=deadline)
        datasets = pipeline.generate_datasets(text, meta, extracted, llm, deadline=deadline)
        recs = pipeline.to_records(meta, datasets)
        all_records.extend(recs)
        all_rag.extend(datasets["rag"])
        all_keywords += meta["keywords"]
        sources.append({"document_name": meta["document_name"], "domain": meta["domain"],
                        "expert": pipeline.route_expert(meta["domain"]), "records": len(recs)})

    # 문서 간 id 충돌 방지를 위해 통합 후 재부여
    for i, r in enumerate(all_records):
        r["id"] = f"{i+1:04d}"
    combined = {
        "instruction": [{"instruction": r["instruction"], "input": r["input"],
                         "output": r["output"], "keyword": r["keyword"]} for r in all_records],
        "qa": [{"question": r["question"], "answer": r["answer"],
                "source": r["source_document"], "keyword": r["keyword"]} for r in all_records],
        "rag": all_rag,
    }
    validation = validate.run_validation(combined, pipeline.to_unsloth_formats(combined), all_records)
    final_records = validation["records"]
    for i, r in enumerate(final_records):  # 중복 제거 후 재ID
        r["id"] = f"{i+1:04d}"

    clean = {
        "instruction": [{"instruction": r["instruction"], "input": r["input"],
                         "output": r["output"], "keyword": r["keyword"]} for r in final_records],
        "qa": [{"question": r["question"], "answer": r["answer"],
                "source": r["source_document"], "keyword": r["keyword"]} for r in final_records],
        "rag": all_rag,
    }
    unsloth = pipeline.to_unsloth_formats(clean)

    prefix = _domain_prefix(name)
    artifacts = {k: f"{prefix}_{v}" for k, v in {
        "csv": "dataset.csv", "json": "dataset.json", "metadata": "dataset_metadata.json",
        "report": "dataset_report.md", "unsloth_raw": "unsloth_raw.jsonl",
        "unsloth_alpaca": "unsloth_alpaca.jsonl", "unsloth_sharegpt": "unsloth_sharegpt.jsonl",
        "unsloth_chatml": "unsloth_chatml.jsonl",
    }.items()}
    export.write_csv(final_records, os.path.join(out_dir, artifacts["csv"]))
    export.write_json(final_records, os.path.join(out_dir, artifacts["json"]))
    export.write_unsloth(unsloth, out_dir, prefix=prefix)
    export.write_metadata(len(final_records), os.path.join(out_dir, artifacts["metadata"]))

    # 통합 메타로 리포트 작성 + 소스 구성(다양성) 명시
    combined_meta = {"document_name": f"{len(paths)}개 문서 통합", "domain": "법률",
                     "purpose": "다중 법안 소스 통합 데이터셋", "keywords": _dedup(all_keywords)[:12]}
    report_path = os.path.join(out_dir, artifacts["report"])
    export.write_report(combined_meta, validation, report_path)
    with open(report_path, "a", encoding="utf-8") as f:
        f.write("\n## 소스 구성 (다양성)\n")
        f.write(f"- 소스 문서 수: {len(sources)}\n")
        for s in sources:
            f.write(f"- {s['document_name']} — {s['expert']}, {s['records']}행\n")

    return {
        "sources": sources,
        "validation": validation,
        "output_dir": out_dir,
        "artifacts": artifacts,
        "llm_mode": "ollama" if llm.available() else "mock",
    }


def _dedup(seq):
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x); out.append(x)
    return out
