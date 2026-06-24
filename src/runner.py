# 8단계 파이프라인을 순차 오케스트레이션하는 진입점 (TRD §1)
import os

from . import pipeline, synthetic, export, validate
from .config import config
from .llm import LLMClient
from .loaders import load_document


def run(path: str, out_dir: str = None, augment_to_min: bool = True) -> dict:
    out_dir = out_dir or config.output_dir
    os.makedirs(out_dir, exist_ok=True)
    llm = LLMClient()
    document_name = os.path.basename(path)

    # STEP1~2
    text = load_document(path)
    meta = pipeline.analyze(text, document_name, llm)
    expert = pipeline.route_expert(meta["domain"])

    # STEP3
    extracted = pipeline.extract_knowledge(text, meta, llm)

    # STEP4
    datasets = pipeline.generate_datasets(text, meta, extracted, llm)

    # STEP4 보조: 분량 부족 시 합성 증강
    if augment_to_min:
        datasets = synthetic.augment(datasets, config.min_rows)

    # STEP4.5 / STEP5·6 / STEP7
    unsloth = pipeline.to_unsloth_formats(datasets)
    records = pipeline.to_records(meta, datasets)
    validation = validate.run_validation(datasets, unsloth, records)

    # 증강은 raw 행 기준이지만 크기 게이트는 중복 제거 후 기준이라, 원본에
    # 중복쌍이 있으면 행 수가 min_rows 아래로 떨어진다. 중복을 먼저 제거한 뒤
    # 고유 base에서 재증강하면(변형은 항상 고유) 결정적으로 min_rows를 채운다.
    if augment_to_min:
        for _ in range(5):
            deduped_count = validation["row_count"] + validation["quality_filtered"]
            if deduped_count >= config.min_rows:
                break
            datasets = synthetic.dedupe(datasets)
            datasets = synthetic.augment(datasets, config.min_rows)
            unsloth = pipeline.to_unsloth_formats(datasets)
            records = pipeline.to_records(meta, datasets)
            validation = validate.run_validation(datasets, unsloth, records)

    final_records = validation["records"]

    # STEP5/6/8 산출
    export.write_csv(final_records, os.path.join(out_dir, "domain_dataset.csv"))
    export.write_json(final_records, os.path.join(out_dir, "domain_dataset.json"))
    export.write_unsloth(unsloth, out_dir)
    export.write_metadata(len(final_records), os.path.join(out_dir, "dataset_metadata.json"))
    export.write_report(meta, validation, os.path.join(out_dir, "dataset_report.md"),
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
        "llm_mode": "ollama" if llm.available() else "mock",
    }
