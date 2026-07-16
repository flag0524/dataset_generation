# STEP5/6/8 산출물 직렬화: CSV/JSON/Unsloth/리포트/메타데이터
import csv
import json
import os

from .config import config
from .schemas import CSV_COLUMNS


def write_csv(records: list, path: str):
    # UTF-8 BOM(Excel 한글 호환) + 전 필드 QUOTE_ALL. escapechar를 두지 않아(기본값)
    # 백슬래시는 이스케이프하지 않고 문자열 그대로 보존한다(예: LaTeX $\rightarrow$).
    # 따옴표만 doublequote로 처리하므로 값이 원문 그대로 왕복(round-trip)된다.
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, quoting=csv.QUOTE_ALL)
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
        # 자연어 질문. 이전에는 CSV에만 있어 마스터 JSON·학습 변환본에서 유실됐다.
        "question": r.get("question", ""),
        "instruction": r["instruction"],
        "input": r["input"],
        "output": r["output"],
        "metadata": {
            "source": r["source_document"],
            "keyword": r["keyword"],
            # 근거성(어휘): output이 '소스 문서 전체'와 공유하는 토큰 비율.
            # grounded는 아래 grounding_threshold(어휘 기준) 대비 판정이며,
            # 리포트의 공공기관 기준 0.80은 '엔티티(사실) 근거성'에 적용되는 별개 지표다.
            # 두 값을 혼동하지 않도록 임계값과 방법을 데이터에 함께 기록한다.
            "grounding": r.get("grounding"),
            "grounded": r.get("grounded"),
            "grounding_threshold": config.grounding_min,
            "grounding_method": "lexical_token_overlap(output, source_document)",
            # 방법론 Entity 검증: 조문·금액·날짜·법령명·기관명을 규칙(정규식)으로 추출해
            # 소스 문서 전체와 대조한다. hallucinated_entities = 문서에 없는 엔티티.
            "entity_grounding": r.get("entity_grounding"),
            "entity_grounding_method": "regex_entity_match(output, source_document)",
            "hallucinated_entities": r.get("hallucinated_entities", []),
            "source_span": r["input"],  # 근거 원문 구간(=input, 해당 청크)
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
    gs = validation.get("mean_gold_semantic")
    gm = validation.get("gold_matched", 0)
    hr = validation.get("hallucination_rate", 0)
    dr = validation.get("duplicate_rate", 0)
    score = validation["quality_score"]

    # OCR 판정: 자기비교(source_span==input)로는 입증할 수 없으므로, ① OCR을 실제로 썼는지와
    # ② 썼다면 독립 측정(텍스트레이어 vs 렌더+OCR)한 문자 정확도를 그대로 노출한다.
    _ocr = meta.get("ocr") or {}
    _m = _ocr.get("measure") or {}
    if not _ocr.get("used"):
        ocr_val, ocr_ok = "OCR 미사용(텍스트 레이어 추출)", None
    elif _m.get("pages"):
        ocr_val = f"{_m['accuracy']}% (CER {_m['cer']}, {_m['pages']}쪽 독립 측정)"
        ocr_ok = _m["accuracy"] >= config.std_ocr
    else:
        ocr_val, ocr_ok = f"OCR 사용({_ocr.get('ocr_pages')}쪽) — 미측정(OCR_EVAL=1로 측정)", None

    rows = [
        ("최종 품질", f"{config.std_quality}점 이상(A)", f"{score}점 ({validation.get('grade', '-')})",
         score >= config.std_quality),
        ("엔티티 근거성(Grounding)", f"{config.std_grounding} 이상",
         f"{eg}" if eg is not None else "N/A(엔티티 없음)", None if eg is None else eg >= config.std_grounding),
        ("의미 유사도", f"{config.std_semantic} 이상",
         f"{ms}" if ms is not None else "N/A(SEMANTIC_ENABLED=1로 측정)", None if ms is None else ms >= config.std_semantic),
        ("의미 유사도(gold 기준)", f"{config.std_semantic} 이상",
         f"{gs} ({gm}건 매칭)" if gs is not None else "N/A(GOLD_PATH·소스 겹침 필요)",
         None if gs is None else gs >= config.std_semantic),
        ("환각 의심율", f"{config.std_hallucination_max}% 이하", f"{hr}%", hr <= config.std_hallucination_max),
        ("중복률", f"{config.std_duplicate_max}% 이하", f"{dr}%", dr <= config.std_duplicate_max),
        ("메타데이터 완전성", "100%", "100%" if validation.get("metadata_complete") else "미완",
         bool(validation.get("metadata_complete"))),
        ("OCR 정확도", f"{config.std_ocr}% 이상", ocr_val, ocr_ok),
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
        f"- 환각 조문 제거: {validation.get('hallucinated_articles_dropped', 0)}건 "
        "(원문에 없는 조문 인용 레코드 삭제)",
        f"- 초단답(30자 미만): {validation.get('short_answer_count', 0)}건 (검수 권장)",
    ]
    _rw = validation.get("rewrite")
    if _rw and _rw.get("targeted"):
        lines.append(
            f"- 저근거 재작성: 대상 {_rw['targeted']}건 중 **{_rw['rewritten']}건 채택** "
            f"(평균 근거성 {_rw['mean_before']} → **{_rw['mean_after']}**). "
            "근거성이 실제로 오르고 새 환각이 없을 때만 채택."
        )
    lines += [
        f"- 부정문 의미반전 위험: {validation.get('negation_mismatch_count', 0)}건 "
        "(원문 부정어가 답변에서 사라짐 — 검수 우선)",
    ]
    # 검증 설계 투명성: 어떤 임계값·방법으로 잰 값인지 데이터와 함께 명시한다.
    # (grounded 플래그와 공공기관 0.80 기준이 서로 다른 지표라는 점을 오해하지 않도록.)
    rows_n = validation["row_count"]
    uniq_in = validation.get("unique_inputs", 0)
    per_input = round(rows_n / uniq_in, 1) if uniq_in else 0
    lines += [
        "",
        "## 검증 설정 (재현·해석용)",
        f"- 어휘 근거성: `grounding` = output↔**소스 문서 전체**의 토큰 중첩 비율. "
        f"`grounded` 판정 임계값 **{config.grounding_min}** (LLM이 재진술하므로 어휘 일치는 낮은 게 정상).",
        f"- 엔티티(사실) 근거성: 조문·금액·날짜·법령명·기관명을 규칙(정규식)으로 추출해 소스 문서와 대조. "
        f"공공기관 기준 **{config.std_grounding}**은 이 지표에 적용되며 `grounded` 플래그와는 **별개 지표**다.",
        "- 환각 판정: 위 규칙 기반 엔티티 대조로 '문서에 없는 엔티티'를 표시(LLM 심판 아님). "
        "원문 PDF 대조가 아닌 추출 텍스트 대조이므로 OCR 오류는 별도 측정이 필요하다.",
        f"- 중복률 정의: **제거된 중복 레코드 수 ÷ 전체 레코드 수** "
        f"({validation.get('duplicates_removed', 0)}/{validation.get('duplicates_removed', 0) + rows_n} 기준, "
        "질문·답변 완전일치 쌍 제거).",
        "- OCR 정확도: `source_span`은 `input`과 같은 값이라 **자기비교로는 입증 불가**. 대신 "
        "**독립 측정**한다 — PDF 텍스트 레이어(참조) vs 같은 쪽을 300DPI로 렌더링해 OCR한 결과(가설)의 "
        "CER/WER. 텍스트 레이어가 있는 PDF는 OCR을 쓰지 않으므로 'OCR 미사용'으로 표기한다. "
        "(참고: Tesseract 한국어 실측 문자 정확도는 60%대로 기준 99%에 크게 못 미치므로, "
        "**스캔 PDF 입력은 텍스트 품질 저하를 감수해야 한다**.)",
        "",
        "## 다양성 (학습 시 암기·누수 위험 판단용)",
        f"- 소스 문서 수: {validation.get('unique_sources', 0)} / 고유 원문 청크(input): **{uniq_in}개**",
        f"- 청크당 평균 레코드: **{per_input}건** (같은 원문이 여러 과제 앵글로 반복 등장)",
        f"- 학습/검증 분할은 **원문 청크(또는 소스 문서) 단위**로 하십시오. "
        "같은 input이 서로 다른 분할에 들어가면 데이터 누수가 발생합니다.",
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
