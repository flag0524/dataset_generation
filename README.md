# 도메인 특화 데이터셋 생성 시스템

업무 문서를 입력하면 도메인을 분석하고 지식을 추출해 **Unsloth 파인튜닝용 학습 데이터셋**(CSV/JSON + Raw/Alpaca/ShareGPT/ChatML)을 생성·검증하는 시스템이다.

## 스택
- Python 3.11
- 웹 UI: FastAPI + 정적 HTML/JS
- LLM: 로컬 Ollama (미가용 시 mock 폴백)
- 검증 루프: 자체 구현 (Validator + LLM Judge + 크기/구조 점검)

## 설치 & 실행
```bash
pip install -r requirements.txt

# 1) 파이프라인 단독 실행
python -c "from src.runner import run; run('samples/sample_admin.txt')"
# → output/ 에 산출물 생성

# 2) 웹 UI
uvicorn web.app:app --reload   # http://localhost:8000

# 3) 테스트
python -m pytest tests/ -q
```

환경 변수: `OLLAMA_HOST`, `OLLAMA_MODEL`, `OUTPUT_DIR`, `CHAT_TEMPLATE`.

## 파이프라인 (8단계)
문서 로딩 → 분석/도메인 분류 → 전문가 라우팅 → 지식·규칙 추출 → 데이터셋 생성(+합성 증강) → Unsloth 포맷 변환 → CSV/JSON Export → 검증 루프 → 버전·리포트.

## 산출물 (`output/`)
- `domain_dataset.csv`, `domain_dataset.json`
- `unsloth_{raw,alpaca,sharegpt,chatml}.jsonl`
- `dataset_metadata.json`, `dataset_report.md`

## 문서
설계·계획·검증 문서는 `docs/`에 있다 — PRD, TRD, goal, plan, status, tests, context-notes.

## 한계
- HWP는 best-effort(미리보기 스트림) 추출이며 완전 지원이 아니다.
- OCR은 Tesseract 별도 설치 필요.
- 현재 지식 추출은 규칙·휴리스틱 기반이며, Ollama 연결 시 LLM 추출로 고도화 가능.
