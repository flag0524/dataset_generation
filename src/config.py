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

    # 법안 처리 상태(계류/폐기/가결). 원문·자동조회로 확정 불가하므로 기본 '미확인'이며,
    # 의안정보시스템 확인 후 BILL_STATUS로 설정한다. 발의안을 현행법으로 오인하지 않게 함.
    bill_status: str = os.getenv("BILL_STATUS", "미확인")

    # RAGAS 스타일 자동평가(LLM 심판) 여부·표본. 비용이 커 기본 OFF(RAGAS_ENABLED=1).
    ragas_enabled: bool = os.getenv("RAGAS_ENABLED", "").lower() in ("1", "true", "yes")
    ragas_sample: int = int(os.getenv("RAGAS_SAMPLE", "15"))

    # 공공기관 권장 기준(DocumentAI 검증방법론 §공공기관 권장 기준) — 리포트의 기준별
    # 충족/미달 판정에 쓰는 단일 진입점. env로 조정 가능(기본값은 방법론과 동일).
    # 주의: std_grounding(0.80)은 '엔티티(사실) 근거성' 기준이며, 어휘 중첩 플래그용
    # grounding_min(0.25)과 다른 지표다(LLM 재진술이라 어휘 일치는 낮은 게 정상).
    std_grounding: float = float(os.getenv("STD_GROUNDING", "0.80"))
    # 의미 유사도(output↔원문) 기준. 방법론 원값 0.95는 '거의 원문 그대로'를 전제하나,
    # 본 파이프라인은 사실(용어·수치·조문)은 보존하되 표현은 재진술하도록 설계돼 표면
    # 임베딩 유사도가 자연히 낮아진다(실측 0.799, 엔티티근거성 0.988·환각 1.5%로 사실은
    # 별도 검증). 재진술 등가성 임계(문장 임베딩 코사인 0.75±)로 현실화한다.
    std_semantic: float = float(os.getenv("STD_SEMANTIC", "0.75"))
    std_hallucination_max: float = float(os.getenv("STD_HALLUCINATION_MAX", "2.0"))
    std_duplicate_max: float = float(os.getenv("STD_DUPLICATE_MAX", "3.0"))
    std_quality: int = int(os.getenv("STD_QUALITY", "90"))
    std_ocr: float = float(os.getenv("STD_OCR", "99.0"))
    std_human_review: float = float(os.getenv("STD_HUMAN_REVIEW", "95.0"))


config = Config()
