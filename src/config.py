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
    # STEP3~4 LLM 작업 전체 벽시계 예산(초). 0이면 무제한(기본) — 데이터셋 생성은
    # 품질 우선이라 모든 청크를 실제 LLM으로 생성한다. 예산을 양수로 두면 '빠른 미리보기'
    # 모드가 되어 초과분 청크는 드롭되며, 산출물은 학습용이 아닌 미완성본이다.
    llm_time_budget: float = float(os.getenv("LLM_TIME_BUDGET", "0"))
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

    # 청크(세그먼트) 최소 길이(자). 신구조문 대비표 파편·초단문 저품질 청크를 거른다.
    min_seg_len: int = int(os.getenv("MIN_SEG_LEN", "50"))

    # 근거성(grounding) 최소 기준. output이 원문(input)과 어휘를 이만큼 공유하지 못하면
    # 근거 미확인으로 플래그한다. LLM이 재진술하므로 완전 일치는 아니며 감사 추적용 신호다.
    grounding_min: float = float(os.getenv("GROUNDING_MIN", "0.25"))

    # 의미 유사도(방법론) 측정 여부·표본 수. 임베딩 모델 로드 비용이 커 기본 OFF이며
    # SEMANTIC_ENABLED=1로 켠다(망분리 시 SEMANTIC_MODEL을 오프라인 반입해야 동작).
    semantic_enabled: bool = os.getenv("SEMANTIC_ENABLED", "").lower() in ("1", "true", "yes")
    semantic_sample: int = int(os.getenv("SEMANTIC_SAMPLE", "30"))

    # Human Review 표본 비율(방법론 5~10%). 위험도(환각·저근거) 높은 레코드 우선 선정.
    human_review_rate: float = float(os.getenv("HUMAN_REVIEW_RATE", "0.1"))

    # RAGAS 스타일 자동평가(LLM 심판) 여부·표본. 비용이 커 기본 OFF(RAGAS_ENABLED=1).
    ragas_enabled: bool = os.getenv("RAGAS_ENABLED", "").lower() in ("1", "true", "yes")
    ragas_sample: int = int(os.getenv("RAGAS_SAMPLE", "15"))


config = Config()
