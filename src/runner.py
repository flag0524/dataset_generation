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

    # STEP4.5
    unsloth = pipeline.to_unsloth_formats(datasets)

    # STEP5/6 레코드화
    records = pipeline.to_records(meta, datasets)

    # STEP7 검증 루프
    validation = validate.run_validation(datasets, unsloth, records)
    final_records = validation["records"]

    # STEP5/6/8 산출
    export.write_csv(final_records, os.path.join(out_dir, "domain_dataset.csv"))
    export.write_json(final_records, os.path.join(out_dir, "domain_dataset.json"))
    export.write_unsloth(unsloth, out_dir)
    export.write_metadata(len(final_records), os.path.join(out_dir, "dataset_metadata.json"))
    export.write_report(meta, validation, os.path.join(out_dir, "dataset_report.md"),
                        extraction_mode=extracted.get("extraction_mode"))

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
