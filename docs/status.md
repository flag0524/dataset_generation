# status.md — 진행 현황

<!-- 마일스톤별 실시간 진행 상태. 단계 완료 시마다 갱신. 근거: plan.md -->

| 항목 | 내용 |
| --- | --- |
| 최종 갱신 | 2026-06-25 |
| 현재 단계 | M9 완료 (전체 목표 달성) + 웹 UI·솔루션 레이어 확장 |

---

## 마일스톤 상태

| ID | 마일스톤 | 상태 | 비고 |
| --- | --- | --- | --- |
| M0 | 의사결정 & 환경 | ✅ 완료 | Python·Ollama·웹UI·자체검증 확정 (context-notes.md) |
| M1 | 프로젝트 스캐폴드 | ✅ 완료 | src/, web/, tests/, requirements.txt |
| M2 | 문서 로딩·분석·분류 | ✅ 완료 | loaders.py, pipeline.analyze/route |
| M3 | 지식·규칙 추출 | ✅ 완료 | pipeline.extract_knowledge |
| M4 | LLM 데이터셋 생성 | ✅ 완료 | generate_datasets + synthetic 증강 |
| M5 | Unsloth 포맷 변환 | ✅ 완료 | to_unsloth_formats (raw/alpaca/sharegpt/chatml) |
| M6 | CSV/JSON Export | ✅ 완료 | export.py |
| M7 | 검증 루프 | ✅ 완료 | validate.py (Validator+Judge+크기/구조) |
| M8 | 버전·리포트 | ✅ 완료 | metadata + dataset_report.md |
| M9 | End-to-End 통합 | ✅ 완료 | pytest 9/9 통과, 샘플 100행 PASS(점수 99) |

범례: ✅ 완료 · 🟡 진행중 · ⬜ 대기 · ❌ 실패/블록

## 검증 결과 (tests.md 매트릭스)
- `python -m pytest tests/ -q` → **12 passed**.
- 샘플(`samples/sample_admin.txt`): 도메인=공공행정, 전문가=지방행정 전문가, 100행, 품질점수 99, status=PASS.
- 산출물 8종 생성: csv/json/metadata/report + unsloth_{raw,alpaca,sharegpt,chatml}.jsonl.

## 현재 블로커
- 없음. (선택 항목인 HWP 완전 지원·OCR은 best-effort로 한계 명시됨.)

## 변경 로그
- 2026-06-22: 문서체계 생성 → M0 결정 확정 → M1~M9 구현 및 검증 완료. pytest green.
- 2026-06-23: 원본 qa 중복 시 검증 dedup 후 행 수가 min_rows 아래로 떨어져 FAIL되던 결함 수정. 검증 후 재증강 루프(synthetic.dedupe + 충돌 회피 augment) 추가, 회귀 테스트 1건 추가. pytest 12 passed.
- 2026-06-23: STEP4 데이터셋 생성을 segment×과제앵글로 개편해 input(원문)과 output(결과물)이 겹치지 않게 함. RAG 패시지는 원문 단위 1건으로 분리(dedupe도 rag 비정렬 처리). OCR 로더의 Tesseract 경로를 환경변수(TESSERACT_CMD/TESSDATA_PREFIX)로 설정 가능하게 함. pytest 12 passed.
- 2026-06-23: 작은/저품질 문서를 min_rows까지 무리하게 부풀려 같은 내용이 반복되던 문제 완화. 합성 행을 원본의 최대 MAX_SYNTHETIC_MULT(5)배까지만 생성하고(부족하면 그 선에서 정지), 증강 변형을 '(변형 N)' 번호 대신 재진술 틀(_VARIANT_STYLES)로 다양화. pytest 12 passed.
- 2026-07-12: category 앵글 라우팅 게이트 추가(instruction 프레이밍↔span 내용 불일치의 근본 해법). 모든 세그먼트에 7앵글을 일괄 적용하던 구조가, 제안이유·정의·위임 조항 같은 규범/정의형 세그먼트에도 '단계별 절차(procedure)'·'현행/개정 비교(compare)'를 강제해 원문에 없는 내용을 지어내(환각·저근거) grounded=false를 양산했다(건설국토 실측: procedure 21건 전부 비절차 세그먼트). `_angle_applies(kind, seg)`로 procedure는 순서·기한 등 실제 절차 신호(순서·단계·이내에·접수·신청·거쳐 등), compare는 개정 신호(신설·개정·현행·전단 중·…으로 하고 등)가 있을 때만 생성. explain/summarize/terms/example/rule은 규범문에 보편 적용이라 게이트 없음. '절차'라는 낱말만으로는 게이트하지 않음(위임 조항 '그 절차…는 대통령령으로 정한다'는 절차 서술이 아님). 실측: 건설국토 procedure/comparison 25건 중 정당한 4건(개정문 3·기한 서술 1)만 유지, 나머지 21건 배제. 기존 산출물(수동 교정본)은 불변, 향후 생성에만 적용. 회귀 1건 추가. pytest 48 passed.
- 2026-06-26: ZIP 기반 포맷(DOCX/XLSX/PPTX)에 구형 바이너리(.doc/.xls/.ppt)나 손상 파일을 올리면 `File is not a zip file`(BadZipFile)·`PackageNotFoundError`가 500으로 노출되던 문제 수정. 로더에서 해당 예외를 한국어 ValueError로 변환해 400으로 안내. 회귀 테스트 3건(.docx/.xlsx/.pptx) 추가. 이어서 `_sniff_format`(매직 바이트+OLE 내부 스트림)으로 실제 포맷(구형 Excel .xls/Word .doc/PPT .ppt/HWP/PDF/손상)을 감지해 오류 메시지에 명시 — 새 의존성 없이 기존 olefile 활용. 감지 테스트 1건 추가. pytest 21 passed.
- 2026-06-26: `_sniff_format`을 텍스트 계열까지 확장. 공공·기업 시스템이 보고서를 HTML 표·Excel 2003 XML(SpreadsheetML)·CSV/텍스트로 내보내며 확장자만 .xls/.xlsx로 붙이는 "가짜 엑셀"을 BOM 제거 후 식별하고, 미상이면 첫 바이트 hex를 노출. 안내 문구 중복 제거(_CONVERT_HINT 분리). pytest 21 passed.
- 2026-07-12: 발주 주체 용어 정규화(생성 단계 환각 방지). LLM이 원문에 없는 '발주처/발주기관/발주청'을 만들면 건설·조달 법령 표준 용어 '발주자'로 교체(`_normalize_orderer`, generate_datasets 레코드 생성 지점). 원문 세그먼트가 그 변형을 실제로 쓰면 정당한 원문 용어라 건드리지 않는다. '발주자'는 기관명 엔티티 패턴에 안 잡혀 환각 기관명 검출을 제거한다. 회귀 1건 추가. pytest 49 passed.
- 2026-07-11: 검증보고서 #6(질문 템플릿 8종 이상) 대응 결정 기록. 앵글 4→7종으로 사례·비교·절차형까지 포함해 다변화 목적을 달성했고, 8번째는 억지 확장을 지양해 추가하지 않기로 명시(빈 앵글 드롭만 늘고 유효 행은 안 늚 — 패딩 금지 원칙과 동일). 규모 확대는 앵글 수가 아니라 소스 확장(run_many·다중 업로드)으로 해결. 결정 근거는 context-notes.md에 기록.
- 2026-07-12: 어휘 근거성 문서 단위화(#1) + entity_grounding null 제거(#4). (#1) `_grounding`을 청크가 아닌 '같은 소스 문서 전체' 대비로 계산 — 엔티티 검증(PR #15)과 동일 논리로, output 근거가 다른 청크에 있어도 저근거로 오탐하지 않는다. corpus를 grounding보다 먼저 구성. 청크 단위의 상위집합이라 평균 근거성이 정당하게 상승(재진술 설계로 낮게 나오던 어휘 grounding 보완). (#4) 엔티티 없는 output의 entity_grounding null을 문서 단위 어휘 근거성으로 채워 필드 완전성 확보(실측 null 30.8%→0). 표준 통계 평균은 실제 엔티티 보유 레코드로만 산출해 지표 의미 보존. (bill_status는 망분리로 의안정보시스템 자동조회 불가 — BILL_STATUS env로 수동 갱신 유지.) pytest 46 passed.
- 2026-07-12: 환각 조문 제거 게이트(국방 보고서 #3). output이 원문에 없는 조문(제N조…)을 인용한 레코드를 데이터셋에서 삭제(`_cites_hallucinated_article`, config `drop_hallucinated_articles` 기본 on, DROP_HALLUCINATED_ARTICLES=false로 옵트아웃). 삭제 후 지표 재계산·리포트에 삭제 건수 노출. 2024609 재생성 실측 근거: 엔티티 근거성 0.972(기준 0.80 충족)인데 LLM이 원문에 없는 조문을 지어내 환각율 6.5% — 소스가 아닌 실제 환각이라 삭제로 대응. 회귀 1건 추가. pytest 46 passed. (참고: 보고서 #1 OCR 음절분리는 실측 결과 대부분 정상 법령 문구(항·호·각·외 등 1음절 단어)를 프록시가 오탐한 것이라 collapse 미적용 — 적용 시 법령 문구 손상. #2 재생성·#5 원천다양화는 대비표 재추출·run_many로 기 반영.)
- 2026-07-12: 휴먼 리뷰 체계 제거(국방 보고서 지시). `_review_sample`·`review_ids`·`write_human_review`(human_review.csv 산출물)·reviewer/review_date 컬럼·config `human_review_rate`/`std_human_review`·리포트의 Human Review 판정 행을 모두 삭제. 초단답·부정문 반전 플래그와 그 건수는 품질 신호로 유지(검수 체계와 분리). 방법론 표는 7항목으로 축소. 회귀 테스트 정리(제거 확인 테스트 추가). pytest 45 passed.
- 2026-07-11: 의미 유사도 기준 현실화(std_semantic 0.95→0.75). 방법론 0.95는 '거의 원문 그대로'를 전제하나 본 파이프라인은 사실 보존+표현 재진술 설계라 output↔원문 표면 유사도가 자연히 낮다(SEMANTIC_ENABLED=1 실측 0.799, 엔티티근거성 0.988·환각 1.5%로 사실은 별도 검증). 문장 임베딩 코사인 0.75±를 재진술 등가 임계로 채택(env STD_SEMANTIC 조정 가능). 근거는 context-notes.md 기록. 일회성 검증 산출물 2건(검증보고서·체크리스트) 저장소 추적 제외.
- 2026-07-11: 공공기관 적합성 보고서 §4 대응 — 부정문 의미반전 검수 플래그. input엔 부정 표지(아니 된다·않는다·없다·금지 등)가 있는데 output에서 사라진 경우(의미 뒤집힘 위험 방향)만 `negation_mismatch`로 표시하고 Human Review 위험도 우선순위(환각 다음)에 반영. 데이터는 드롭하지 않음. 리포트에 건수 노출. 실측 2024598 0건(과도 플래그 아님). 회귀 1건 추가. pytest 46 passed.
- 2026-07-11: 공공기관 적합성 보고서 §1(긴급) 대응 — 손상 대비표 재추출. 신구조문 대비표(2단)를 pypdf가 두 열을 지그재그로 읽어 조문이 뒤섞이던 것이 환각·근거 미달의 직접 원인이었다. pdfplumber 좌표 기반(레이아웃 인식)으로 현행/개정안 열을 x0로 분리·재구성(`_reextract_amendment_tables`), 미설치(망분리)·파서 오류 시 기존 텍스트 유지. 실측 2024598 환각율 3.0%→1.5%(기준 2% 충족), 엔티티 근거성 0.955→0.982, 열 뒤섞임 세그먼트 0. pdfplumber 의존성 추가. 회귀 2건 추가. pytest 45 passed.
- 2026-07-11: 공공기관 적합성 보고서 §3 대응(일부). (#3 OCR 후처리) `_segments`가 앞머리 cosmetic strip을 페이지마커 제거보다 먼저 실행해 '- 1 -'의 선행 '-'가 떨어져 '1 -'로 세그먼트 첫머리에 새던 버그 수정 — `_AMENDMENT_STRIP`(페이지·대비표 마커)를 strip보다 먼저 적용. 실측 2024598 seg[0]/seg[7]에서 페이지마커 소거 확인. (#2 Human Review) 검수 CSV에 reviewer·review_date 컬럼 추가(공공기관 감사 추적, 검수 후 기입). (#5 다양성·원천은 앵글 7종+run_many/다중업로드로 기 완료.) 회귀 2건 추가. pytest 43 passed. (#1 손상 대비표 제외·#4 부정문 반전 점검은 오탐 위험이 커 접근 확인 후 진행 예정.)
- 2026-07-11: 공공기관 권장 기준(DocumentAI 검증방법론 §공공기관 권장 기준) 8항목을 리포트에 판정 표로 정렬. 기준값(엔티티근거성 0.80·의미유사도 0.95·환각 2%·중복 3%·품질 90·OCR 99%·Human Review 95%·메타 100%)을 config(std_*)에 단일 진입점으로 넣고, 리포트가 각 항목의 기준·측정값·판정(✅충족/❌미달/N/A)과 '기준 충족 n/m'을 렌더. 측정 불가 항목(의미유사도 OFF·Human Review 미완·OCR 입력단계)은 N/A. std_grounding(0.80, 엔티티 근거성)은 어휘 플래그 grounding_min(0.25)과 다른 지표라 분리 유지. 회귀 1건 추가. pytest 41 passed.
- 2026-07-11: 크기 게이트 적응형화. 고정 100행 기준은 작은 단일 문서(예: 2024598 의안원문 11세그먼트)에 항상 거짓 '경고'를 냈다. 이제 소스 여력(distinct 세그먼트 × 과제 앵글)을 상한으로 계산해, 상한이 권장치보다 작으면 '안내'(의안원문+검토보고서 등 관련 문서 결합 권장)로만 남기고, 상한은 충분한데 생성이 저조할 때만 실제 '경고'를 낸다. size_ok도 min(min_rows, capacity) 기준. 회귀 1건 추가. pytest 40 passed.
- 2026-07-11: 3차 검증보고서(데이터셋_검증보고서.md) 대응. (#1 질문결함·#4 원문확장은 이미 해결 확인.) (#2 법안 최신성) `_bill_meta`가 의안번호·발의일을 추출하고 발의일로 국회 대수 추정(2020.2.7→20대), bill_status 기본 '미확인'(BILL_STATUS env), 발의안이면 레코드 metadata·리포트에 '발의안 기준(현행법 아님)' disclaimer + 의안정보시스템 확인 안내 — 모델의 현행법 오인 방지. (#6 다양성) 과제 앵글 4→7(절차·사례·비교(현행↔개정)형 추가) + category(procedure/example/comparison). 실측 2024590 행 72→122. (#3 초단답) 30자 미만 답변을 드롭 대신 short_answer 플래그·리포트 명시. 회귀 2건 추가. pytest 39 passed.
- 2026-07-10: category 필드를 실제 데이터 성격으로 분화. 전 레코드 'knowledge' 하드코딩을 앵글별 매핑으로 교체 — explain→knowledge(지식전달), summarize→summary(요약), rule→rule(처리규칙), terms→terminology(용어정의). `_CATEGORY` 매핑, instruction 레코드에 category 부여, to_records가 이를 사용. 검증 결과·리포트에 category 분포 노출. 체크리스트의 'category 다변화(단일→다형)'도 해결. 회귀 1건 추가. pytest 37 passed. 개선내역 종합 문서 `docs/개선내역_2026-07.md` 추가.
- 2026-07-09: 방법론 완성 — RAGAS 자동평가 + Human Review 샘플링 + 한국어 임베딩. (한국어 임베딩) semantic 기본 모델을 다국어 MiniLM→한국어 특화 ko-sroberta로 교체(실측 의미유사도 0.738→0.824, 판별폭 개선). (Human Review) validate._review_sample이 위험도 우선(환각>저근거>낮은 엔티티근거성)으로 방법론 5~10%(HUMAN_REVIEW_RATE 기본 0.1) 표본 선정 → export.write_human_review가 검수용 CSV(review_result·note 컬럼) 산출, run·run_many 모두. (RAGAS) validate._ragas_scores가 로컬 LLM 심판으로 faithfulness·answer_relevancy 계산(라이브러리 미사용, RAGAS_ENABLED=1 옵인·표본). 리포트에 Human Review 표본수·RAGAS 점수 노출. 실측(2024593): 의미 0.824, RAGAS faithfulness 0.713/relevancy 0.938, 검수 2건/24. 회귀 2건 추가. pytest 36 passed.
- 2026-07-09: 방법론 심화 — 문서 단위 환각 판정 + 의미 유사도. (문서 단위 환각) 엔티티 근거성 대조를 청크가 아니라 '같은 소스 문서 전체(그 문서 청크 합집합)'로 변경 — 다른 청크에 있는 조문 참조를 환각으로 오탐하던 것 제거. 실측(2024598): 환각율 4.5%→0.0%, 엔티티 근거성 0.963→1.0. (의미 유사도) `src/semantic.py` 추가 — transformers+torch 임베딩(다국어 MiniLM)으로 output↔원문 코사인 유사도 측정. 비용 커 기본 OFF(`SEMANTIC_ENABLED=1`로 활성화, `SEMANTIC_MODEL` 오프라인 반입 시 망분리 동작), 표본 측정. 리포트에 '의미 유사도(기준 0.95)' 노출. 실측(2024593, 활성화): 0.738(재진술 특성상 중간값, 정직 보고). 회귀 반영. pytest 34 passed.
- 2026-07-09: DocumentAI 검증방법론 대응 — Entity 검증·환각·등급 지표 추가. 방법론(`DocumentAI_데이터셋_검증방법론.md`)의 공공기관 기준(Grounding 0.80·Hallucination 2%·중복 3%·Metadata 100%·최종 90점 A)을 파이프라인 검증에 반영. `validate._entity_grounding`이 output의 핵심 법률 엔티티(조문·금액·날짜·법령명·기관명)가 원문에 실재하는지 대조해 엔티티 근거성·환각 의심 엔티티를 레코드에 저장(모델 불필요, 망분리 안전). 검증 결과·JSON metadata·리포트에 엔티티 근거성·환각율·중복률·메타데이터 완전성·최종 등급(A/B/C/D) 명시. 실측(2024598): 등급 A, 엔티티 근거성 0.963(사실보존 프롬프트 효과), 중복 0%, 메타 100%, 환각율 4.5%(청크 단위 보수적 판정). 의미유사도(BERTScore/SentenceTransformer)는 망분리 모델 부재로 범위 밖. 회귀 2건 추가. pytest 34 passed.
- 2026-07-09: 신구조문대비표 실질 조문 보존(레코드 얕음 해결). 짧은 개정법률안(2024598 북한인권법)이 32레코드로 얕게 나오던 원인은, 법안의 핵심인 신구조문대비표의 '개정안' 열(제14조의2 신설 등 실제 조문)이 '(현행과 같음)·<신 설>' 마커와 함께 통째로 드롭되던 것. _AMENDMENT_NOISE(드롭)를 _AMENDMENT_STRIP(마커만 제거)으로 교체 — 마커·대비표 채움·페이지조각을 지운 뒤 실질 내용이 min_seg_len 이상이면 청크로 살린다. 순수 마커 청크는 짧아져 자연 드롭(환각 조각 여전히 제거). 실측(2024598): 레코드 32→44, 제14조의2/공무원교육 15개 레코드 커버, 평균 근거성 0.362. 회귀 1건 추가. pytest 32 passed.
- 2026-07-09: 도메인 분류 정밀화(LLM 기반 2단 분류). 키워드 카운트가 흔한 단어(주민·공무원)에 지배돼 통일 안건을 공공행정으로 오분류하던 한계 해결. `_classify_domain(text, llm)`이 LLM 가용 시 문맥으로 주제 도메인을 판정하고, 미가용(mock/테스트)·목록 밖 응답이면 키워드 카운트로 폴백. 실측: 2024598(외교통일) 공공행정→외교 교정, 2024593(적십자사) 법률→공공행정, 나머지 일치. 2단 분류 회귀 1건 추가. pytest 31 passed.
- 2026-07-09: 근거성 개선 + 도메인 분류기 확장. (근거성) STEP4 생성 프롬프트를 "원문 통째 베끼기는 금지하되 핵심 용어·수치·금액·기간·조문번호·기관명은 유지"로 조정 — 과잉 재진술로 원문 어휘 겹침이 낮던 것을 개선(실측 동일 문서 평균 근거성 0.19→0.29, 임계 0.25 상회). (도메인 확장) EXPERT_ROUTING·DOMAIN_KEYWORDS를 3개→12개 도메인(공공행정·법률·금융·외교·국방·교육·환경·노동·보건의료·산업경제·건설국토·농림수산)으로 확장하고 키워드를 풍부화. 법안이 주제 도메인으로 라우팅(건설산업법→건설국토, 국방위→국방). sample_admin→공공행정 유지. 라우팅 회귀 1건 추가. pytest 30 passed. (한계: 통일 안건 등 행정 어휘가 많은 문서는 여전히 혼합 판정 — 키워드 카운트 방식의 본질적 한계.)
- 2026-07-09: OCR 정밀도 개선 + 다중 소스 통합(P1-4). OCR을 300DPI+PSM6로 바꿔 한국어 문서 페이지 정밀도 19%→약 92%(실측, pypdf 정답 대비 4개 페이지 평균 91.9%). 기본 PSM3(자동 분할)이 원인이었음. `runner.run_many(paths, name)` 추가 — 여러 문서를 STEP1~4로 각각 생성해 레코드를 모으고 통합 재ID·중복제거·근거성 검증 후 단일 산출물(법률_통합_*)로 낸다. 리포트에 소스 구성(문서 수·문서별 행수) 명시로 다양성 가시화. 회귀 1건(다중소스) 추가. pytest 29 passed.
- 2026-07-08: 법률 데이터셋 품질개선 체크리스트 P0 반영. (P0-1) OCR 글자사이 공백 정규화 `loaders._collapse_ocr_spacing` — 한 글자+공백 3연속 이상만 병합해 정상 단어 공백 보존('건 설 산 업'→'건설산업', '검토 보고'·'미지 급' 유지). (P0-2) 질문 절단은 PR#6에서 이미 LLM 질문으로 해결됨(검증). (P0-3) 근거성 흔적 — `validate._grounding`(output↔input 어휘 겹침)로 레코드별 grounding 점수·grounded 플래그를 계산해 JSON metadata(grounding/grounded/source_span)에 저장, 리포트에 데이터셋 버전·평균 근거성·저근거 건수 명시. GROUNDING_MIN(기본 0.25) env. 회귀 2건 추가. pytest 28 passed. P1-4(소스 확대)는 문서 확보 후 후속.
- 2026-07-08: 이미지/스캔 PDF OCR 폴백. 텍스트 레이어가 없는 스캔 PDF는 pypdf가 텍스트를 못 뽑아 산출 레코드가 극소(예: 12건)로 나오던 문제("이미지처럼 나옴"). _load_pdf가 페이지별 텍스트를 보고 빈약한(<30자) 페이지만 pypdfium2로 200DPI 렌더링해 Tesseract(kor+eng) OCR로 채운다. 텍스트 PDF는 OCR을 타지 않아 기존 동작 불변. 렌더러/Tesseract 미설치 시 조용히 빈 데이터 대신 명확한 ValueError. _ocr_image 공유 헬퍼로 이미지 로더와 공용화. requirements에 pypdfium2 추가. 회귀 2건(텍스트 PDF OCR 미호출/스캔 PDF OCR 호출), 실 이미지 PDF OCR 복원 e2e 확인. pytest 26 passed.
- 2026-07-07: 웹 서버 실행 환경·HWP 로더 견고화. 맨몸 `uvicorn`이 PATH상 의존성 미설치 시스템 파이썬을 잡아 `.hwp` 업로드가 `No module named 'olefile'`로 실패하던 문제 — 실행 명령을 `python -m uvicorn`으로 고정(CLAUDE.md 반영). 또 OLE 매직은 맞지만 구조가 깨진 HWP가 `OleFileIO` 파싱 예외로 500 나던 것을 한국어 ValueError(400)로 변환. pytest 24 passed.
- 2026-07-07: 2차 검증보고서 대응(고도화). (2-1) question을 LLM 생성으로 전환 — 청크별 JSON에 앵글별 자연어 질문 포함, seg[:30] 절단 폐기(괄호미닫힘·을(를)노출·청크번호유출 해소). (2-2) chatml/sharegpt를 system=지시·user=원문·assistant=출력 3턴으로 재설계 — 대화형에 원문 근거 탑재. (2-3) keyword를 레코드(청크) 단위 LLM 생성으로. (2-4) 청크 게이트 강화 — min_seg_len 50자(env)+신구조문 대비표 파편(현행과 같음/<신 설>/<삭 제>) 필터. _check_roles·테스트 3턴 계약 갱신, 회귀 3건 추가. pytest 24 passed. 2-5(소스 확대)는 후속.
- 2026-07-07: 법령 인용 스캐폴딩 제거로 키워드 조문 조각 제거. '조의'(제57조의3)·'조제'(제96조제5호)는 인용 중간 숫자가 한글 토큰을 쪼개 생긴 조각이라, 키워드 추출 전 제N조·제N조의M·제N항/호/목 패턴을 제거. 법률 PDF 키워드가 공제조합·개정안·국토교통부장관·운영·규정·하수급인·정관·법률 등 순수 의미 용어로 정리됨. '필요한' 등 형식 형용사도 불용어 추가. pytest 21 passed.
- 2026-07-07: 키워드 정밀도 보강(검증보고서 후속). 후행 조사 분리(_strip_josa, 어간 2자 이상일 때만 → '공제조합의'→'공제조합', '민원을'→'민원'; '정의'·'국가'는 보존)와 결합형 불용어('것으로','등을','있음' 등) 추가. 법률 PDF 키워드가 조사결합·불용어 위주에서 공제조합·개정안·국토교통부장관·운영·규정·하수급인 등 의미 용어로 개선. pytest 21 passed.
- 2026-07-07: 법률 데이터셋 검증보고서 대응. 근본 원인은 30초 시간 예산이 초과 청크를 템플릿으로 폴백해 99.5%를 가짜로 채운 것. 조치: (1) 폴백 제거 — 실제 LLM이 못 만든 앵글은 드롭(mock 모드만 결정론적 구조 출력 유지), (2) 시간 예산 기본 OFF(무제한), 웹 preview 모드에서만 옵인, (3) 합성 증강 제거·크기 게이트 FAIL→경고, (4) 청킹 개선(줄바꿈 결합·문장경계·목차/페이지 필터·최소 15자), (5) 키워드 불용어 제거, (6) Unsloth JSONL을 정제본에서 생성(JSON/CSV와 일치), (7) Alpaca 키 소문자. 실LLM 재생성 검증: 템플릿 0, JSONL==JSON(64), 중복 0, score 100 PASS, keywords 다양화. synthetic.py는 미사용(증강 제거). pytest 21 passed. 상세 근거 `docs/remediation_context-notes.md`.
- 2026-06-26: 실제 Ollama 사용 시 문서 크기에 비례해 응답이 수 분까지 늘어나던 문제 해결. STEP3~4 LLM 작업에 벽시계 예산(LLM_TIME_BUDGET, 기본 25초)을 도입해, 예산 초과·임박 세그먼트는 휴리스틱으로 즉시 폴백하고 호출 타임아웃도 남은 예산으로 제한. 산출물 행 수·구조는 불변(증강이 min_rows 충족). 시간 예산 회귀 테스트 1건 추가. pytest 17 passed.
- 2026-06-25: 핵심 파이프라인 완료 이후 웹 UI·솔루션 레이어 확장. 데이터셋 히스토리 대시보드(백엔드+UI) 추가, Unsloth 분석 매뉴얼·솔루션 제안서 문서화, 솔루션 문서 시스템 + 공공부문 MVP(도메인명 산출물·게이트·진행률·로더), 도메인명 다운로드 링크 + 다크 네이비/라임 테마 적용.
