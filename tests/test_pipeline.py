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


def test_t2_heuristic_mode(result):
    # 테스트 환경(conftest)에서는 LLM 차단 → 휴리스틱 경로
    assert result["extraction_mode"] == "heuristic"


class _StubLLM:
    # gemma4 응답을 흉내내는 stub (네트워크 없이 LLM 파싱 경로 검증)
    def available(self):
        return True

    def generate_json(self, prompt, system="", timeout=None):
        return {
            "knowledge": {f: f"{f} 내용" for f in pipeline.KNOWLEDGE_FIELDS},
            "rules": [
                {"rule_id": "R001", "condition": "민원 접수 시", "action": "7일 내 처리", "exception": "없음"},
                {"condition": "기한 초과 시"},  # rule_id 누락 → 정규화로 보정
                {"action": "무효 규칙"},        # condition 없음 → 제외
            ],
        }


def test_t2_llm_extraction_path():
    meta = {"domain": "공공행정", "purpose": "민원 처리", "keywords": ["민원"], "document_name": "x"}
    out = pipeline.extract_knowledge("민원 접수 시 7일 내 처리해야 한다.", meta, _StubLLM())
    assert out["extraction_mode"] == "llm"
    assert list(out["knowledge"].keys()) == pipeline.KNOWLEDGE_FIELDS
    assert len(out["rules"]) == 2  # 무효 규칙(condition 없음) 제외
    assert all(schemas.validate_rule(r) for r in out["rules"])
    assert out["rules"][1]["rule_id"] == "R002"  # 누락 rule_id 자동 보정


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
    path = os.path.join(result["output_dir"], result["artifacts"]["csv"])
    with open(path, encoding="utf-8-sig") as f:
        header = f.readline().strip().split(",")
    assert header == schemas.CSV_COLUMNS  # T5-1


def test_t5_json_exists(result):
    assert os.path.exists(os.path.join(result["output_dir"], result["artifacts"]["json"]))  # T5-2


# T6 검증 루프
def test_t6_validation(result):
    v = result["validation"]
    assert v["row_count"] >= 100  # T6-3 AC-05
    assert v["quality_score"] >= 90  # T6-4 AC-06
    assert v["status"] == "PASS"
    assert v["format_consistent"] is True  # T6-5


def test_t6_reaugment_on_duplicates(monkeypatch, tmp_path):
    # 원본 qa에 중복쌍이 있으면 중복 제거 후 행 수가 min_rows 아래로 떨어진다.
    # 재증강 루프가 부족분을 채워 크기 게이트를 통과시키는지 검증한다 (회귀).
    from src import runner

    orig = runner.pipeline.generate_datasets

    def dup_datasets(text, meta, extracted, llm, deadline=None):
        ds = orig(text, meta, extracted, llm, deadline=deadline)
        for i in range(10):  # 앞쪽 10개 qa를 동일 쌍으로 덮어써 중복 9개를 강제
            ds["qa"][i] = dict(ds["qa"][0])
        return ds

    monkeypatch.setattr(runner.pipeline, "generate_datasets", dup_datasets)
    v = runner.run(SAMPLE, out_dir=str(tmp_path))["validation"]
    # 재증강 루프가 중복을 정리하고 부족분을 채워 크기 게이트를 통과해야 한다.
    assert v["size_ok"] is True
    assert v["row_count"] >= 100
    assert v["status"] == "PASS"


# 응답 시간 게이트: 느린 LLM이라도 시간 예산이 벽시계를 유계로 만든다 (회귀)
def test_s_t4_time_budget_bounds_wallclock():
    import time

    class _SlowLLM:
        def __init__(self):
            self.calls = 0

        def available(self):
            return True

        def generate_json(self, prompt, system="", timeout=None):
            self.calls += 1
            time.sleep(0.4)  # 느린 호출 모사
            return {"explain": "x" * 20, "summarize": "y" * 20,
                    "rule": "z" * 20, "terms": "w" * 20}

    segs = [f"세그먼트 내용 번호 {i} 입니다." for i in range(40)]
    extracted = {"segments": segs}
    meta = {"domain": "일반", "document_name": "x", "keywords": ["민원"]}
    slow = _SlowLLM()

    # 예산 없이 40개를 동시성 5로 돌리면 8배치 × 0.4초 = 약 3.2초.
    # 1초 예산이면 첫 배치만 LLM 처리되고 나머지는 휴리스틱으로 폴백해야 한다.
    deadline = time.monotonic() + 1.0
    t0 = time.monotonic()
    ds = pipeline.generate_datasets("", meta, extracted, slow, deadline=deadline)
    elapsed = time.monotonic() - t0

    assert elapsed < 2.5  # 예산이 동작하면 8배치를 다 돌지 않는다
    assert slow.calls < len(segs)  # 일부 세그먼트는 LLM 호출 없이 폴백
    assert len(ds["instruction"]) == len(segs) * len(pipeline._TASKS)  # 행 수는 그대로
    assert all(schemas.validate_instruction(d) for d in ds["instruction"])


# 로더: ZIP 컨테이너 포맷(.docx/.xlsx/.pptx)에 비-ZIP 바이트가 오면
# 영문 BadZipFile 대신 깨끗한 한국어 ValueError로 변환한다 (회귀)
@pytest.mark.parametrize("ext", [".docx", ".xlsx", ".pptx"])
def test_s_t6_loader_badzip_to_valueerror(tmp_path, ext):
    from src.loaders import load_document

    f = tmp_path / f"bad{ext}"
    f.write_bytes(b"\xd0\xcf\x11\xe0not a zip at all")  # 구형 OLE 매직 모사
    with pytest.raises(ValueError, match="유효한"):
        load_document(str(f))


# 로더: 실제 포맷 감지 메시지가 오류에 포함된다 (정체 확인)
def test_s_t6_sniff_detects_real_format(tmp_path):
    from src.loaders import _sniff_format

    pdf = tmp_path / "x.bin"
    pdf.write_bytes(b"%PDF-1.4 ...")
    assert "PDF" in _sniff_format(str(pdf))

    ole = tmp_path / "y.bin"
    ole.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest")
    assert "OLE" in _sniff_format(str(ole))

    z = tmp_path / "z.bin"
    z.write_bytes(b"PK\x03\x04junk")
    assert "ZIP" in _sniff_format(str(z))

    html = tmp_path / "h.bin"
    html.write_bytes(b"<html><body><table><tr><td>1</td></tr></table></body></html>")
    assert "HTML" in _sniff_format(str(html))

    txt = tmp_path / "t.bin"
    txt.write_bytes("이름,부서\n홍길동,총무과\n".encode("utf-8"))
    assert "텍스트" in _sniff_format(str(txt)) or "CSV" in _sniff_format(str(txt))


# T7 산출물 & 통합
def test_t7_artifacts(result):
    out = result["output_dir"]
    a = result["artifacts"]
    for key in ["csv", "json", "unsloth_chatml", "unsloth_alpaca", "metadata", "report"]:
        assert os.path.exists(os.path.join(out, a[key])), a[key]  # T7-1/3


# S-T1 산출물 파일명이 도메인 업무명 접두를 따르는지 (solution_tests.md)
def test_s_t1_domain_prefixed_filenames(result):
    domain = result["meta"]["domain"]
    a = result["artifacts"]
    assert a["csv"].startswith(f"{domain}_"), a["csv"]
    assert a["json"] == f"{domain}_dataset.json"
    assert a["unsloth_alpaca"] == f"{domain}_unsloth_alpaca.jsonl"


# S-T4 검증 게이트 임계값이 환경변수로 조정되는지 (solution_tests.md)
def test_s_t4_gate_thresholds_env(monkeypatch):
    import importlib
    from src import config as cfg
    monkeypatch.setenv("MIN_ROWS", "250")
    monkeypatch.setenv("QUALITY_PASS_SCORE", "77")
    importlib.reload(cfg)
    try:
        assert cfg.config.min_rows == 250
        assert cfg.config.quality_pass_score == 77
    finally:
        monkeypatch.undo()
        importlib.reload(cfg)  # 기본값 복원
    assert cfg.config.min_rows == 100


# S-T5 진행률 콜백이 단계별로 호출되는지 (solution_tests.md)
def test_s_t5_progress_callback(tmp_path):
    events = []
    run(SAMPLE, out_dir=str(tmp_path), on_progress=events.append)
    assert len(events) >= 1
    assert events[0]["step"] == 1
    assert events[-1]["step"] == events[-1]["total"]  # 마지막 단계까지 도달
    assert all("stage" in e for e in events)


# S-T6 로더 폴백: 추출 불가 입력은 명확한 메시지로 ValueError (solution_tests.md)
def test_s_t6_loader_clear_fallback(tmp_path):
    from src.loaders import load_document
    # 지원하지 않는 포맷
    f = tmp_path / "x.bin"
    f.write_bytes(b"\x00\x01")
    with pytest.raises(ValueError):
        load_document(str(f))
    # HWP 확장자지만 OLE가 아님 → 명확한 메시지
    h = tmp_path / "doc.hwp"
    h.write_bytes(b"not-an-ole-file")
    with pytest.raises(ValueError, match="HWP"):
        load_document(str(h))
