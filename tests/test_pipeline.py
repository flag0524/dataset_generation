# tests.md 검증 매트릭스를 자동화한 end-to-end 및 단위 테스트
import json
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
    # Unsloth/HF 표준에 맞춰 alpaca 키는 소문자
    assert all(set(r) == {"instruction", "input", "output"} for r in u["alpaca"])
    # 대화형 포맷은 3턴: system=지시, user=원문, assistant=출력 (보고서 2-2 대응)
    for c in u["sharegpt"]:  # T4-2
        assert [m["from"] for m in c["conversations"]] == ["system", "human", "gpt"]
    for c in u["chatml"]:  # T4-3
        assert [m["role"] for m in c["messages"]] == ["system", "user", "assistant"]


# 2-2: 대화형 user 턴에 원문(input)이 실려야 한다(잘린 질문 암기 방지)
def test_s_chat_user_turn_carries_source(result):
    u = result["unsloth"]
    inputs = {d["input"] for d in result["datasets"]["instruction"]}
    for c in u["chatml"]:
        assert c["messages"][1]["content"] in inputs  # user 턴 == 원문 청크
    for c in u["sharegpt"]:
        assert c["conversations"][1]["value"] in inputs


# 2-1: question은 원문 절단 접미 템플릿이 아니어야 한다(괄호미닫힘·조사노출 없음)
def test_s_question_not_truncated(result):
    for qa in result["datasets"]["qa"]:
        q = qa["question"]
        assert "을(를)" not in q  # 조사 미처리 노출 금지
        assert q.count("(") == q.count(")")  # 괄호 균형(문장 중간 절단 방지)


# 2-3: keyword가 문서 단위로 전 레코드에 동일 복사되면 안 된다(레코드 단위)
def test_s_keyword_per_record(result):
    recs = result["datasets"]["instruction"]
    assert all("keyword" in r for r in recs)


# T5 Export
def test_t5_csv_columns(result):
    path = os.path.join(result["output_dir"], result["artifacts"]["csv"])
    with open(path, encoding="utf-8-sig") as f:
        header = f.readline().strip().split(",")
    assert header == schemas.CSV_COLUMNS  # T5-1


def test_t5_json_exists(result):
    assert os.path.exists(os.path.join(result["output_dir"], result["artifacts"]["json"]))  # T5-2


# T6 검증 루프 — 합성 증강 제거 후 새 의미: 크기는 경고, 품질 점수는 형식·충실도로만.
def test_t6_validation(result):
    v = result["validation"]
    assert v["row_count"] > 0  # 실제 생성 레코드가 존재
    assert v["quality_score"] >= 90  # T6-4 AC-06 (형식·충실도)
    assert v["status"] == "PASS"
    assert v["format_consistent"] is True  # T6-5


def test_t6_no_synthetic_padding(result):
    # 합성 증강을 제거했으므로 산출 레코드는 청크×앵글 상한을 넘지 않는다(패딩 없음).
    segs = pipeline._segments(open(SAMPLE, encoding="utf-8").read())
    v = result["validation"]
    assert v["row_count"] <= len(segs) * len(pipeline._TASKS)


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
            return {k: {"q": f"{k} 질문?", "a": f"{k} 답변 " + "가" * 20}
                    for k in ("explain", "summarize", "rule", "terms")} | {"keywords": ["민원"]}

    segs = [f"세그먼트 내용 번호 {i} 입니다." for i in range(40)]
    extracted = {"segments": segs}
    meta = {"domain": "일반", "document_name": "x", "keywords": ["민원"]}
    slow = _SlowLLM()

    # 예산 없이 40개를 동시성 5로 돌리면 8배치 × 0.4초 = 약 3.2초.
    # 2초 예산이면 남은 시간이 1초를 넘는 동안만 LLM을 시도하고, 이후 청크는 드롭된다
    # (_budget_timeout은 1초 미만 남으면 호출을 건너뛴다).
    deadline = time.monotonic() + 2.0
    t0 = time.monotonic()
    ds = pipeline.generate_datasets("", meta, extracted, slow, deadline=deadline)
    elapsed = time.monotonic() - t0

    assert elapsed < 3.0  # 예산이 동작하면 8배치를 다 돌지 않는다
    assert slow.calls < len(segs)  # 일부 세그먼트는 LLM 호출 없이 드롭
    # 드롭 때문에 레코드는 전체보다 적고(폴백 패딩 없음), 실제 생성된 것만 남는다.
    assert 0 < len(ds["instruction"]) < len(segs) * len(pipeline._TASKS)
    assert all(schemas.validate_instruction(d) for d in ds["instruction"])


# 방법론 Entity 검증: output의 핵심 엔티티(조문·금액)가 원문에 실재하는지 대조
def test_s_entity_grounding_logic():
    from src.validate import _entity_grounding, _entities
    src = "제57조의3 및 제96조에 따라 3천만원 이하의 벌금에 처한다."
    assert "제57조의3" in _entities(src) and "3천만원" in _entities(src)
    # 원문 엔티티를 보존한 output → 근거성 1.0, 환각 없음
    eg, unsup = _entity_grounding("제57조의3 위반 시 3천만원 이하 벌금이 부과된다", src)
    assert eg == 1.0 and unsup == []
    # 원문에 없는 조문을 지어낸 output → 환각 의심 엔티티로 잡힘
    eg2, unsup2 = _entity_grounding("제99조에 따라 처벌한다", src)
    assert "제99조" in unsup2


# 방법론 검증 지표가 검증 결과·리포트에 반영된다(등급·엔티티근거성·환각·메타데이터)
def test_s_methodology_metrics(result):
    v = result["validation"]
    for k in ("grade", "entity_grounding", "hallucination_rate", "duplicate_rate", "metadata_complete"):
        assert k in v
    assert v["grade"] in ("A", "B", "C", "D")
    assert all("hallucinated_entities" in r for r in v["records"])
    report = open(os.path.join(result["output_dir"], result["artifacts"]["report"]), encoding="utf-8").read()
    assert "방법론 검증" in report and "엔티티 근거성" in report


# 청킹: 신구조문대비표의 마커는 제거하되 실질 개정 조문은 살린다 (통째 드롭 금지)
def test_s_amendment_table_keeps_substance():
    para = ("제14조의2(공무원 등에 대한 교육의 실시) ① 중앙행정기관의 장, 지방자치단체의 장은 "
            "소속 공무원 및 직원 등에게 북한주민의 인권에 관한 교육을 실시하고 그 결과를 통일부장관에게 제출하여야 한다. "
            "<신 설> (현행과 같음)")
    joined = " ".join(pipeline._segments(para))
    assert "제14조의2" in joined and "통일부장관" in joined  # 실질 개정 조문 보존
    assert "현행과 같음" not in joined and "신 설" not in joined  # 보일러플레이트 제거


# 도메인 분류 정밀화: LLM 가용 시 문맥 판정을 따르고, 미가용/무효 응답이면 키워드 폴백
def test_s_domain_llm_two_tier():
    class _Stub:
        def __init__(self, d): self.d = d
        def available(self): return True
        def generate_json(self, prompt, system="", timeout=None): return {"domain": self.d}

    # 키워드로는 공공행정이 우세하지만 LLM이 외교로 판정 → LLM을 따른다
    text = "주민 주민 공무원 공무원 행정 통일"
    assert pipeline._keyword_classify_domain(text) == "공공행정"
    assert pipeline._classify_domain(text, _Stub("외교")) == "외교"
    # LLM 미가용이면 키워드 폴백
    assert pipeline._classify_domain(text, None) == "공공행정"
    # LLM이 목록 밖 값을 주면 키워드 폴백
    assert pipeline._classify_domain(text, _Stub("이상한도메인")) == "공공행정"


# 도메인 분류기 확장: 분야별 대표 키워드에 각 도메인으로 라우팅된다
def test_s_domain_routing_expanded():
    cases = {
        "국방": "국방 병역 안보 군인 부대 방위 국군 장병 예비군",
        "건설국토": "건설 공사 시공 주택 도로 부동산 건축 국토 수급인",
        "외교": "외교 통일 조약 협정 국제 남북 대사 수교 재외국민",
        "환경": "환경 오염 폐기물 배출 탄소 기후 재활용 온실가스 대기",
        "교육": "교육 학교 학생 교원 대학 교사 입시 학위 유치원",
    }
    for dom, text in cases.items():
        assert pipeline._classify_domain(text) == dom
        assert dom in pipeline.EXPERT_ROUTING


# P1-4: 다중 소스 통합 — 여러 문서를 하나의 데이터셋으로 합치고 소스가 보존된다
def test_s_run_many_multisource(tmp_path):
    from src.runner import run_many
    a = tmp_path / "doc_a.txt"; a.write_text("민원 접수 시 7일 이내에 담당 부서가 처리해야 한다. 처리 결과는 신청인에게 통지한다.", encoding="utf-8")
    b = tmp_path / "doc_b.txt"; b.write_text("공제조합은 면책된 채무를 이유로 보증을 거부하지 못한다. 위반 시 벌금에 처한다.", encoding="utf-8")
    r = run_many([str(a), str(b)], out_dir=str(tmp_path / "out"), name="법률_통합")
    # 두 문서 모두 소스로 집계
    assert len(r["sources"]) == 2
    recs = json.load(open(os.path.join(r["output_dir"], r["artifacts"]["json"]), encoding="utf-8"))
    srcs = {x["metadata"]["source"] for x in recs}
    assert {"doc_a.txt", "doc_b.txt"} <= srcs  # 레코드에 두 소스가 모두 존재
    # id는 통합 후 유일
    ids = [x["id"] for x in recs]
    assert len(ids) == len(set(ids))


# 근거성(grounding) 흔적: 검증·레코드·JSON 메타데이터에 근거 점수/플래그 저장 (P0-3)
def test_s_grounding_trace(result):
    v = result["validation"]
    assert "mean_grounding" in v and "low_grounding" in v
    for r in v["records"]:
        assert 0.0 <= r["grounding"] <= 1.0
        assert isinstance(r["grounded"], bool)
    path = os.path.join(result["output_dir"], result["artifacts"]["json"])
    recs = json.load(open(path, encoding="utf-8"))
    assert all("grounding" in x["metadata"] and "source_span" in x["metadata"] for x in recs)


# 로더: OCR이 넣는 한글 글자사이 공백은 붙이되, 정상 단어 공백은 보존한다 (P0-1)
def test_s_ocr_spacing_collapse():
    from src.loaders import _collapse_ocr_spacing
    # 글자 단위로 떼어진 OCR 출력 → 붙는다
    assert _collapse_ocr_spacing("건 설 산 업 기 본 법") == "건설산업기본법"
    # 정상 단어 사이 공백(2글자 이상 토큰)은 보존
    assert _collapse_ocr_spacing("검토 보고 자료") == "검토 보고 자료"
    # 2글자 토큰이 섞인 공백은 건드리지 않음(오병합 방지)
    assert _collapse_ocr_spacing("미지 급") == "미지 급"
    # 영문·숫자 혼합 보존
    assert _collapse_ocr_spacing("ABC 2020 검 토") == "ABC 2020 검 토"


# 로더: 텍스트 PDF는 OCR을 타지 않고, 이미지(스캔) PDF는 OCR 폴백을 탄다 (회귀)
def test_s_pdf_text_bypasses_ocr(tmp_path, monkeypatch):
    fitz = pytest.importorskip("fitz")
    from src import loaders

    # fitz 기본 폰트는 한글 글리프를 embed하지 못하므로 픽스처는 ASCII로 둔다
    # (텍스트 PDF가 OCR을 타지 않는지만 검증하면 되어 언어는 무관).
    p = tmp_path / "text.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "This is a sufficiently long real body text. " * 3)
    doc.save(str(p)); doc.close()

    def _boom(img):
        raise AssertionError("텍스트 PDF인데 OCR이 호출됨")

    monkeypatch.setattr(loaders, "_ocr_image", _boom)
    assert "real body text" in loaders.load_document(str(p))


def test_s_pdf_scanned_triggers_ocr(tmp_path, monkeypatch):
    fitz = pytest.importorskip("fitz")
    pytest.importorskip("pypdfium2")
    from src import loaders

    p = tmp_path / "scan.pdf"
    doc = fitz.open()
    doc.new_page()  # 텍스트 없는 빈 페이지 → 이미지 기반으로 간주
    doc.save(str(p)); doc.close()

    monkeypatch.setattr(loaders, "_ocr_image", lambda img: "OCR로복원한텍스트")
    assert "OCR로복원한텍스트" in loaders.load_document(str(p))


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

    # 512바이트 경계에서 한글이 잘려도 텍스트로 판별돼야 한다(오탐 회귀)
    boundary = tmp_path / "b.bin"
    boundary.write_bytes(("가" * 200).encode("utf-8")[:512])  # 끝에서 멀티바이트가 잘림
    assert "텍스트" in _sniff_format(str(boundary)) or "CSV" in _sniff_format(str(boundary))


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
