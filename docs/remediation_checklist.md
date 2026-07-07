<!-- 법률 데이터셋 검증보고서 대응 — 파이프라인 품질 개선 체크리스트 -->
# 데이터셋 품질 개선 체크리스트 (법률 검증보고서 대응)

근거: `docs/법률_데이터셋_검증보고서.md`. grill(2026-07-07)로 방향 확정. 상세 근거는 `docs/remediation_context-notes.md`.

## 결정 요약 (grill 결과)
- 품질 우선, 30초 SLA 포기 → 생성은 무제한, 긴 작업은 후속 백그라운드.
- 폴백 템플릿 제거 → LLM 답변 없는 청크는 드롭(패딩 금지).
- min_rows 합성 증강 제거 → 크기 게이트는 FAIL 대신 경고.
- 이번 범위: 파이프라인 코드 수정 + `sample_admin.txt`로 검증. 웹 백그라운드·다중소스·법률 재생성(PDF 필요)은 후속.
- `LLM_TIME_BUDGET`: 기본 OFF(무제한), 명시적 미리보기 모드에서만 사용하고 산출물을 "미리보기·학습용 아님"으로 라벨.

## 코드 수정
- [ ] 폴백 제거 — `pipeline._derive_outputs`: LLM 미가용/빈 응답/저품질 시 해당 앵글 레코드 드롭. `_heuristic_output`을 생성 경로에서 제거.
- [ ] 시간 예산 기본 OFF — `config.llm_time_budget` 기본 무제한. 웹 `/api/generate`에 `preview` 플래그(기본 off) 추가, preview에서만 예산 적용 + 라벨.
- [ ] 증강 제거 — `runner`에서 `synthetic.augment`/재증강 루프 제거. `validate`의 크기 미달을 FAIL이 아니라 경고(issues)로.
- [ ] 청킹 개선 — `pipeline._segments`: 줄바꿈으로 끊긴 문장 결합, 문장경계 분할, 목차 점선(`·····`/dot leader)·페이지번호 필터, 최소 길이 상향.
- [ ] 키워드 재구현 — `pipeline._top_keywords`: 한국어 불용어(조사·접속사) 제거, 긴 명사형 우선. 외부 NLP 의존성 없이(망분리).
- [ ] JSONL 정제 순서 — `runner`: `unsloth`를 정제 후 최종 레코드에서 생성(정제 전 `datasets` 아님).
- [ ] Alpaca 키 소문자 — `pipeline.to_unsloth_formats`: `instruction/input/output`.

## 검증
- [ ] `test_t4_formats`(대문자 키 단언) 등 계약 변경 테스트 갱신.
- [ ] 크기·PASS·점수 단언(`test_t6_*`) 새 의미(증강 없음)로 갱신.
- [ ] `run('samples/sample_admin.txt')` 무제한 실행 → 템플릿 문장 0, 키워드 다양성, JSONL 건수==JSON, Alpaca 소문자 확인.
- [ ] `python -m pytest tests/ -q` 통과.

## 후속(이번 범위 밖)
- [ ] 법률 데이터셋 전체 재생성(원본 PDF `2024590_국토교통위원회_검토보고서.pdf` 확보 후).
- [ ] 웹 백그라운드 잡 + 진행률(긴 생성용).
- [ ] 소스 다중화 + RAGAS 검증.
