# tests.md 검증 매트릭스를 자동화한 end-to-end 및 단위 테스트
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import pipeline, schemas
from src.runner import run

SAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples", "sample_admin.txt")


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    return run(SAMPLE, out_dir=str(out))


# T1 문서 분석
def test_t1_metadata_schema(result):
    assert schemas.validate_metadata(result["meta"])  # T1-2


def test_t1_domain_routing(result):
    assert result["meta"]["domain"] == "공공행정"  # T1-3
    assert result["expert"] == "지방행정 전문가"


# T2 지식·규칙
def test_t2_rule_schema(result):
    assert result["rules"], "규칙이 추출되어야 함"
    assert all(schemas.validate_rule(r) for r in result["rules"])  # T2-1


# T3 LLM 데이터셋
def test_t3_dataset_schemas(result):
    ds = result["datasets"]
    assert all(schemas.validate_instruction(d) for d in ds["instruction"])  # T3-1
    assert all(schemas.validate_qa(d) for d in ds["qa"])  # T3-2
    assert all(schemas.validate_rag(d) for d in ds["rag"])  # T3-3


# T4 Unsloth 포맷
def test_t4_formats(result):
    u = result["unsloth"]
    assert all("text" in r for r in u["raw"])  # T4-1
    assert all(set(r) == {"Instruction", "Input", "Output"} for r in u["alpaca"])
    for c in u["sharegpt"]:  # T4-2
        assert [m["from"] for m in c["conversations"]] == ["human", "gpt"]
    for c in u["chatml"]:  # T4-3
        assert [m["role"] for m in c["messages"]] == ["user", "assistant"]


# T5 Export
def test_t5_csv_columns(result):
    path = os.path.join(result["output_dir"], "domain_dataset.csv")
    with open(path, encoding="utf-8-sig") as f:
        header = f.readline().strip().split(",")
    assert header == schemas.CSV_COLUMNS  # T5-1


def test_t5_json_exists(result):
    assert os.path.exists(os.path.join(result["output_dir"], "domain_dataset.json"))  # T5-2


# T6 검증 루프
def test_t6_validation(result):
    v = result["validation"]
    assert v["row_count"] >= 100  # T6-3 AC-05
    assert v["quality_score"] >= 90  # T6-4 AC-06
    assert v["status"] == "PASS"
    assert v["format_consistent"] is True  # T6-5


# T7 산출물 & 통합
def test_t7_artifacts(result):
    out = result["output_dir"]
    for name in ["domain_dataset.csv", "domain_dataset.json",
                 "unsloth_chatml.jsonl", "unsloth_alpaca.jsonl",
                 "dataset_metadata.json", "dataset_report.md"]:
        assert os.path.exists(os.path.join(out, name)), name  # T7-1/3
