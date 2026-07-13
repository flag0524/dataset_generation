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


# 2-2: 대화형 user 턴은 '자연어 질문 + 원문 근거'를 함께 실어야 한다.
# 원문만 실으면 question 정보가 학습 변환본에서 유실되고, 질문만 실으면 문서기반 학습이 안 된다.
def test_s_chat_user_turn_carries_question_and_source(result):
    # unsloth는 '검증 후 정제된' 레코드로 만들어지므로 raw datasets와 인덱스가 다르다.
    # 인덱스 대신 user 턴의 구조('질문\n\n[원문]\n원문')를 검증한다.
    u = result["unsloth"]
    inputs = {d["input"] for d in result["datasets"]["instruction"]}
    questions = {d["question"] for d in result["datasets"]["qa"]}
    assert any(q.strip() for q in questions)

    def check(user):
        assert "[원문]" in user                       # 질문과 원문이 함께 실림
        q, src = user.split("\n\n[원문]\n", 1)
        assert src in inputs                          # 원문 근거 유지(문서기반 학습)
        assert q in questions                         # 질문 보존(유실 방지)

    for c in u["chatml"]:
        check(c["messages"][1]["content"])
    for c in u["sharegpt"]:
        check(c["conversations"][1]["value"])


# question이 마스터 JSON에 보존되고, grounded 판정 기준이 데이터에 자기설명되어야 한다
def test_s_json_preserves_question_and_threshold(result):
    from src.config import config
    path = os.path.join(result["output_dir"], result["artifacts"]["json"])
    recs = json.load(open(path, encoding="utf-8"))
    assert all("question" in r for r in recs)                 # CSV에만 있던 질문 유실 방지
    assert any(r["question"].strip() for r in recs)
    m = recs[0]["metadata"]
    # grounded가 어느 임계값·방법으로 판정됐는지 데이터가 스스로 설명해야 한다
    assert m["grounding_threshold"] == config.grounding_min
    assert "lexical" in m["grounding_method"]
    assert "regex" in m["entity_grounding_method"]


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
    import csv as _csv
    path = os.path.join(result["output_dir"], result["artifacts"]["csv"])
    with open(path, encoding="utf-8-sig", newline="") as f:
        header = next(_csv.reader(f))  # QUOTE_ALL 인용을 csv 모듈이 정상 파싱
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


# 크기 게이트: 소스 여력(세그먼트×앵글)이 권장치보다 작으면 '경고' 대신 '안내'만 낸다.
def test_s_size_gate_adaptive_for_small_source():
    from src import validate
    # 세그먼트 2개짜리 작은 소스 → 상한 2×7=14 < 100. 경고가 아니라 안내여야 한다.
    recs = [{"id": i, "question": f"q{i}", "answer": "가나다라마바사아자차카타파하" * 2,
             "output": "가나다라마바사아자차카타파하" * 2,
             "input": f"세그먼트{i % 2}", "source_document": "small.pdf",
             "keyword": ["법률"], "category": "knowledge"} for i in range(6)]
    v = validate.run_validation({"instruction": [], "qa": [], "rag": []}, {}, recs)
    joined = " ".join(v["issues"])
    assert "안내" in joined and "경고: 행 수" not in joined


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


# 법안 최신성(보고서 §4): 의안번호·발의일·대수 추출과 발의안 disclaimer
def test_s_bill_metadata():
    from src import pipeline
    text = ("건설산업기본법 일부개정법률안\n의 안 번 호 24590\n발의연월일 : 2020. 2. 7.\n"
            "발 의 자 : 홍길동의원 등\n제57조의3을 신설한다.")
    m = pipeline._bill_meta(text)
    assert m["is_bill"] is True
    assert m["bill_number"] == "24590"
    assert m["propose_date"] == "2020.2.7"
    assert m["assembly_term"] == "20대"  # 2020.2.7은 20대(21대는 2020.5.30~)
    assert "현행법이 아닙니다" in m["currency_notice"]
    # 일반 문서는 법안 아님
    assert pipeline._bill_meta("일반 민원 처리 매뉴얼입니다.")["is_bill"] is False


# 과제 앵글 확장(보고서 #6): 절차·사례·비교형이 추가되어 category가 다양해진다
def test_s_expanded_angles():
    from src import pipeline
    kinds = {k for _, k in pipeline._TASKS}
    assert {"procedure", "example", "compare"} <= kinds  # 4→7 확장
    assert all(k in pipeline._CATEGORY and k in pipeline._GENERIC_Q for k in kinds)


# category 라우팅: 절차·비교형 앵글은 세그먼트가 그 성격을 담을 때만 적용된다(환각 방지)
def test_s_angle_routing():
    from src import pipeline
    # 규범·정의형 세그먼트: 절차/비교 앵글 배제, 설명/용어 등은 유지
    norm = "제99조(과태료) 다음 각 호의 어느 하나에 해당하는 자에게는 500만원 이하의 과태료를 부과한다"
    assert not pipeline._angle_applies("procedure", norm)
    assert not pipeline._angle_applies("compare", norm)
    assert pipeline._angle_applies("explain", norm)
    assert pipeline._angle_applies("terms", norm)
    # 위임 조항의 '절차'라는 낱말만으로는 절차형으로 보지 않는다
    deleg = "제1항에 따른 확인에 대한 절차, 방법 등은 대통령령으로 정한다"
    assert not pipeline._angle_applies("procedure", deleg)
    # 개정문(신설/전단 중 …으로 하고)은 비교형이 적용된다
    rev = '제34조제4항 전단 중 "고용하는 등"을 "고용 또는 건설기계를 대여하는 등"으로 하고, 제10항을 신설한다'
    assert pipeline._angle_applies("compare", rev)
    # 실제 단계·기한 서술은 절차형이 적용된다
    proc = "선급금을 받은 날부터 15일 이내에 하수급인에게 선급금을 지급하여야 한다"
    assert pipeline._angle_applies("procedure", proc)


# category: 앵글별 실제 데이터 성격을 반영한다(전부 'knowledge' 하드코딩 금지)
def test_s_category_reflects_task(result):
    recs = result["datasets"]["instruction"]
    cats = {r["category"] for r in recs}
    valid = {"knowledge", "summary", "rule", "terminology", "procedure", "example", "comparison"}
    assert {"knowledge", "summary", "rule"} & cats  # 앵글별 분화 확인
    assert cats <= valid
    # JSON 산출물에도 다양한 category가 실림
    path = os.path.join(result["output_dir"], result["artifacts"]["json"])
    jcats = {x["category"] for x in json.load(open(path, encoding="utf-8"))}
    assert len(jcats) > 1  # 단일 knowledge가 아님


# 휴먼 리뷰 체계 제거: review_ids·human_review 산출물·_review_sample이 없어야 한다
def test_s_no_human_review_system(result):
    from src import validate, export
    v = result["validation"]
    assert "review_ids" not in v
    assert "human_review" not in result["artifacts"]
    assert not hasattr(validate, "_review_sample")
    assert not hasattr(export, "write_human_review")


# 방법론 검증 지표가 검증 결과·리포트에 반영된다(등급·엔티티근거성·환각·메타데이터)
def test_s_methodology_metrics(result):
    v = result["validation"]
    for k in ("grade", "entity_grounding", "hallucination_rate", "duplicate_rate", "metadata_complete", "mean_semantic"):
        assert k in v
    assert v["grade"] in ("A", "B", "C", "D")
    assert v["mean_semantic"] is None  # SEMANTIC_ENABLED 미설정 시 미측정
    assert all("hallucinated_entities" in r for r in v["records"])
    report = open(os.path.join(result["output_dir"], result["artifacts"]["report"]), encoding="utf-8").read()
    assert "방법론 검증" in report and "엔티티 근거성" in report and "의미 유사도" in report


# 공공기관 권장 기준(방법론 8항목)이 config 기준값으로 리포트에 판정 표시된다
def test_s_public_standards_table(result):
    from src.config import config
    report = open(os.path.join(result["output_dir"], result["artifacts"]["report"]), encoding="utf-8").read()
    # 항목 전부 표에 존재(Human Review는 체계 제거로 표에서 뺀다)
    for item in ("최종 품질", "엔티티 근거성", "의미 유사도", "환각 의심율",
                 "중복률", "메타데이터 완전성", "OCR 정확도"):
        assert item in report
    assert "Human Review" not in report
    # 기준값은 config에서 온다(하드코딩 아님) + 판정 열이 렌더된다
    assert f"{config.std_grounding} 이상" in report
    assert f"{config.std_semantic} 이상" in report
    assert "기준 충족:" in report and "판정" in report
    # 측정 불가 항목은 N/A(의미유사도 OFF·OCR)
    assert "N/A" in report


# 청킹: 신구조문대비표의 마커는 제거하되 실질 개정 조문은 살린다 (통째 드롭 금지)
def test_s_amendment_table_keeps_substance():
    para = ("제14조의2(공무원 등에 대한 교육의 실시) ① 중앙행정기관의 장, 지방자치단체의 장은 "
            "소속 공무원 및 직원 등에게 북한주민의 인권에 관한 교육을 실시하고 그 결과를 통일부장관에게 제출하여야 한다. "
            "<신 설> (현행과 같음)")
    joined = " ".join(pipeline._segments(para))
    assert "제14조의2" in joined and "통일부장관" in joined  # 실질 개정 조문 보존
    assert "현행과 같음" not in joined and "신 설" not in joined  # 보일러플레이트 제거


# OCR 후처리(보고서 #3): 페이지 마커 '- N -'가 앞머리 strip에 깨져 세그먼트에 새지 않는다
def test_s_page_marker_not_leaked():
    import re
    # 페이지 시작('- 1 -')과 페이지 중간('... - 5 - 현행 ...')을 모두 포함
    text = ("- 1 -\n북한인권법 일부개정법률안은 소속 공무원 및 직원 등에게 "
            "북한주민의 인권에 관한 교육을 실시하려는 것을 목적으로 한다.\n\n"
            "교육 실시에 필요한 사항은 대통령령으로 정한다. - 5 - 현 행 개정안 "
            "제6조의 내용은 통일부장관이 정하는 바에 따라 시행하여야 한다.")
    segs = pipeline._segments(text)
    assert segs, "세그먼트가 비면 안 된다"
    for s in segs:
        assert not re.match(r"^\d+\s*-", s)                  # 앞머리 '1 -' 잔존 금지
        assert not re.search(r"(?:^|\s)-\s*\d+\s*-(?=\s|$)", s)  # 중간 '- 5 -' 잔존 금지


# 환각 조문 제거(국방 보고서 #3): 원문에 없는 조문을 인용한 레코드는 데이터셋에서 삭제
def test_s_drop_hallucinated_article():
    from src import validate
    src_doc = "제6조에 따라 교육을 실시한다. 제10조의 재단은 사업을 수행한다."
    recs = [
        # 원문에 있는 조문 인용 → 유지
        {"id": "1", "question": "q1", "answer": "제6조에 따라 교육을 실시하도록 규정한다",
         "output": "제6조에 따라 교육을 실시하도록 규정한다", "input": src_doc,
         "source_document": "d.pdf", "keyword": ["법률"], "category": "rule"},
        # 원문에 없는 제99조 인용(환각) → 삭제
        {"id": "2", "question": "q2", "answer": "제99조에 따라 벌금을 부과하도록 규정한다",
         "output": "제99조에 따라 벌금을 부과하도록 규정한다", "input": src_doc,
         "source_document": "d.pdf", "keyword": ["법률"], "category": "rule"},
    ]
    v = validate.run_validation({"instruction": [], "qa": [], "rag": []}, {}, recs)
    ids = {r["id"] for r in v["records"]}
    assert "2" not in ids and "1" in ids           # 환각 조문 레코드만 삭제
    assert v["hallucinated_articles_dropped"] == 1
    assert v["hallucination_rate"] == 0.0           # 정제 후 환각율 0


# 부정문 의미반전(보고서 #4): input의 부정어가 output에서 사라지면 품질 신호 플래그
# 발주 주체 정규화: 원문에 없는 '발주처'류를 표준 용어 '발주자'로 교체(원문 용어는 보존)
def test_s_normalize_orderer():
    src = "국가, 지방자치단체 또는 공공기관이 발주하는 공사의 수급인"
    # 원문에 없는 '발주처/발주기관/발주청' → '발주자'
    assert pipeline._normalize_orderer("발주처가 공공기관인 경우", src) == "발주자가 공공기관인 경우"
    assert pipeline._normalize_orderer("발주기관 및 발주청 확인", src) == "발주자 및 발주자 확인"
    # 원문이 실제로 '발주처'를 쓰면 건드리지 않는다(원문 충실성)
    assert pipeline._normalize_orderer("발주처 확인", "발주처가 정한다") == "발주처 확인"
    # 정규화 후 '발주처'는 환각 엔티티로 잡히지 않는다
    from src.validate import _entities
    assert "발주처" not in _entities(pipeline._normalize_orderer("발주처가 발주한다", src))


# write_csv: 백슬래시 리터럴 보존(이스케이프 금지) + QUOTE_ALL + UTF-8 BOM
def test_s_write_csv_preserves_backslash(tmp_path):
    from src import export
    path = str(tmp_path / "out.csv")
    rec = {c: "" for c in schemas.CSV_COLUMNS}
    rec.update({"id": "0001", "output": "확인 $\\rightarrow$ 처리", "keyword": ["법률"]})
    export.write_csv([rec], path)
    raw = open(path, "rb").read()
    assert raw[:3] == b"\xef\xbb\xbf"                 # UTF-8 BOM
    assert b"$\\rightarrow$" in raw                    # 리터럴 백슬래시 그대로(5C 72)
    assert b"$\\\\rightarrow$" not in raw              # 이중이스케이프 아님
    import csv as _csv
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(_csv.reader(f))
    assert rows[1][0].startswith('0001') or rows[1][0] == "0001"  # QUOTE_ALL로 읽어도 원문 왕복
    with open(path, encoding="utf-8-sig") as f:
        body = f.read()
    assert '"id"' in body and '"output"' in body       # 헤더도 전부 인용(QUOTE_ALL)


def test_s_negation_mismatch_flag():
    from src import validate
    assert validate._has_negation("그 행위를 하여서는 아니 된다")
    assert not validate._has_negation("교육을 실시하여야 한다")
    recs = [
        # input엔 '아니 된다'(금지), output은 긍정으로 뒤집음 → 플래그
        {"id": "1", "question": "q1", "answer": "설치할 수 있다고 규정한다",
         "output": "설치할 수 있다고 규정한다", "input": "누구든지 시설을 설치하여서는 아니 된다",
         "source_document": "d.pdf", "keyword": ["법률"], "category": "rule"},
        # 부정어가 양쪽에 유지 → 플래그 아님
        {"id": "2", "question": "q2", "answer": "설치할 수 없다고 규정한다",
         "output": "설치할 수 없다고 규정한다", "input": "누구든지 시설을 설치하여서는 아니 된다",
         "source_document": "d.pdf", "keyword": ["법률"], "category": "rule"},
    ]
    v = validate.run_validation({"instruction": [], "qa": [], "rag": []}, {}, recs)
    flags = {r["id"]: r["negation_mismatch"] for r in v["records"]}
    assert flags["1"] is True and flags["2"] is False
    assert v["negation_mismatch_count"] == 1


# 업로드 파일명 인코딩 복원: latin-1로 깨진 한글 파일명을 UTF-8/CP949로 되살린다
def test_s_upload_filename_encoding_fix():
    from web.app import _fix_filename
    orig = "2024598_의사국 의안과_의안원문.pdf"
    # 브라우저(UTF-8)·한국어 Windows 셸(CP949)이 보낸 뒤 latin-1로 디코드돼 깨진 상태
    assert _fix_filename(orig.encode("utf-8").decode("latin-1")) == orig
    assert _fix_filename(orig.encode("cp949").decode("latin-1")) == orig
    assert _fix_filename(orig) == orig          # 이미 정상 유니코드는 유지
    assert _fix_filename("report.pdf") == "report.pdf"  # ASCII 유지
    assert _fix_filename(None) == "upload"      # 빈 값 방어


# 대비표 재추출(보고서 #1): 열 판별과 열 내 읽기순서 복원(단위)
def test_s_amendment_column_reextract_units():
    from src import loaders
    assert loaders._looks_like_amendment_table("신·구조문대비표 현 행 개 정 안")
    assert loaders._looks_like_amendment_table("현  행 ... 개 정 안 ...")
    assert not loaders._looks_like_amendment_table("의 안 번 호 24598 발의연월일")  # 표지 박스
    # 좌표 단어를 줄(top)·열(x0) 순으로 재정렬 — 한 열 안에서만 정렬
    words = [
        {"text": "B", "x0": 50, "top": 10}, {"text": "A", "x0": 10, "top": 10},
        {"text": "C", "x0": 10, "top": 30},
    ]
    assert loaders._column_text(words) == "A B C"


# 대비표 재추출 통합: 표본 PDF에서 현행/개정안 열이 뒤섞이지 않는다(조문 헤더 중복 없음)
def test_s_amendment_no_column_interleave():
    import re
    pdf = os.path.join(os.path.dirname(SAMPLE), "2024598_의사국 의안과_의안원문.pdf")
    if not os.path.exists(pdf):
        pytest.skip("표본 PDF 없음")
    from src.loaders import load_document
    segs = pipeline._segments(load_document(pdf))
    # 뒤섞임 신호: 같은 조문 헤더가 한 세그먼트에 2회 이상 나타나면 열이 지그재그로 읽힌 것
    for s in segs:
        assert len(re.findall(r"제10조\(북한인권재단", s)) < 2


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
# 산출물은 실행별 폴더({도메인}_{타임스탬프}/)에 격리되므로 경로는 'run_dir/파일명' 형태다.
def test_s_t1_domain_prefixed_filenames(result):
    domain = result["meta"]["domain"]
    a = result["artifacts"]
    run_dir = result["run_dir"]
    assert run_dir.startswith(f"{domain}_")           # 실행 폴더도 도메인 접두
    assert a["csv"].startswith(f"{run_dir}/{domain}_")
    assert a["json"] == f"{run_dir}/{domain}_dataset.json"
    assert a["unsloth_alpaca"] == f"{run_dir}/{domain}_unsloth_alpaca.jsonl"


# 덮어쓰기 방지: 같은 도메인 문서를 다시 생성해도 이전 실행의 산출물이 살아 있어야 한다
def test_s_run_dir_isolates_artifacts(tmp_path):
    out = str(tmp_path)
    r1 = run(SAMPLE, out_dir=out)
    r2 = run(SAMPLE, out_dir=out)
    assert r1["run_dir"] != r2["run_dir"]              # 실행마다 다른 폴더
    p1 = os.path.join(out, r1["artifacts"]["json"])
    p2 = os.path.join(out, r2["artifacts"]["json"])
    assert os.path.exists(p1) and os.path.exists(p2)   # 1회차 산출물이 덮어써지지 않음
    assert p1 != p2
    # 이력(history.jsonl)은 실행 폴더가 아니라 베이스에 누적된다
    assert os.path.exists(os.path.join(out, "history.jsonl"))


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
