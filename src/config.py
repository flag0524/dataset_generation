# 시스템 전역 설정과 환경 변수 로딩을 담당하는 모듈
import os
from dataclasses import dataclass


@dataclass
class Config:
    # LLM (Ollama) 설정
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "gemma4:31b-cloud")
    # STEP4 세그먼트별 LLM 호출 동시 실행 수 (I/O 대기 단축용)
    llm_concurrency: int = int(os.getenv("LLM_CONCURRENCY", "5"))
    # Ollama 미가용 시 결정론적 mock 모드로 동작 (테스트 가능성 확보)
    use_mock_llm: bool = os.getenv("USE_MOCK_LLM", "auto") != "false"

    # 출력 경로
    output_dir: str = os.getenv("OUTPUT_DIR", "output")

    # 검증 기준 (TRD §5, PRD §9) — 게이트 임계값은 env로 조정 가능(기본값 동일)
    min_rows: int = int(os.getenv("MIN_ROWS", "100"))
    recommended_rows: int = int(os.getenv("RECOMMENDED_ROWS", "1000"))
    quality_pass_score: int = int(os.getenv("QUALITY_PASS_SCORE", "90"))

    # 채팅 템플릿 기본값 (TRD §4.8)
    chat_template: str = os.getenv("CHAT_TEMPLATE", "chatml")


config = Config()
