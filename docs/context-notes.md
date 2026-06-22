# context-notes.md — 결정 기록

<!-- 작업 중 내린 결정과 근거를 누적 기록. 다음 세션이 재유도 없이 이어가도록. -->

## M0 의사결정 (2026-06-22, 사용자 확정)

| 항목 | 결정 | 근거 |
| --- | --- | --- |
| 구현 스택 | **Python** | Unsloth/HF/datasets 생태계 직접 호환 |
| LLM 백엔드 | **로컬 모델 (Ollama)** | 비용·프라이버시. GPU/셋업 필요 |
| 실행 인터페이스 | **웹 UI** | 업로드·검증 루프 시각화 |
| 검증 루프 | **자체 구현** | 의존성 최소화, 제어 용이 |

## 파생 기본값 (Claude 제안, 추후 변경 가능)

| 항목 | 기본값 | 비고 |
| --- | --- | --- |
| 웹 프레임워크 | FastAPI + 정적 HTML/JS | 경량, Python 단일 스택 |
| Ollama 기본 모델 | `gemma4:12b` (설정 변경 가능) | 합성·Judge·추출 공용 |
| PDF 파서 | `pypdf` | |
| DOCX/PPTX/XLSX | `python-docx` / `python-pptx` / `openpyxl` | |
| HWP | `olefile` 기반 best-effort | 완전 지원 어려움, 한계 명시 |
| OCR | `pytesseract` (+Tesseract 설치 필요) | 선택 기능 |
| Markdown/TXT | 직접 로드 | |
| 채팅 템플릿 기본 | `chatml` (선택 가능: llama-3.1/qwen2.5/gemma-3) | |
| 데이터 저장 | 파일 시스템 (`output/`) | DB 미사용 |

## 주의
- LLM 호출이 핵심이라 Ollama 미설치 환경에서는 파이프라인이 stub/mock 모드로 동작하도록 설계(테스트 가능성 확보).
- 스키마 필드명은 TRD §4 고정값 — 변경 금지.
