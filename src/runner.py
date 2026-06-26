# 8단계 파이프라인을 순차 오케스트레이션하는 진입점 (TRD §1)
import os
import re
import time

from . import pipeline, synthetic, export, validate
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


def run(path: str, out_dir: str = None, augment_to_min: bool = True, on_progress=None) -> dict:
    out_dir = out_dir or config.output_dir
    os.makedirs(out_dir, exist_ok=True)
    llm = LLMClient()
    document_name = os.path.basename(path)

    # 실제 LLM을 쓸 때만 STEP3~4에 벽시계 예산을 건다. mock은 이미 빠르므로 무제한.
    deadline = time.monotonic() + config.llm_time_budget if llm.available() else None

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

    # STEP4
    _emit(5)
    datasets = pipeline.generate_datasets(text, meta, extracted, llm, deadline=deadline)

    # STEP4 보조: 분량 부족 시 합성 증강
    if augment_to_min:
        datasets = synthetic.augment(datasets, config.min_rows)

    # STEP4.5 / STEP5·6 / STEP7
    _emit(6)
    unsloth = pipeline.to_unsloth_formats(datasets)
    records = pipeline.to_records(meta, datasets)
    _emit(7)
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
