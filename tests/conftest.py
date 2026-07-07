# 테스트를 결정론적으로 유지하기 위해 LLM 호출을 차단하고 휴리스틱 추출로 폴백시킨다
import os

# 도달 불가능한 호스트로 지정 → LLMClient.available()가 False → 휴리스틱 경로
os.environ.setdefault("OLLAMA_HOST", "http://127.0.0.1:1")

# 소형 샘플(sample_admin.txt)은 문장이 짧아 프로덕션 기본 50자로는 청크가 전부 걸러진다.
# 테스트는 구조 검증이 목적이므로 임계값을 낮춘다(프로덕션 기본값 50은 그대로).
os.environ.setdefault("MIN_SEG_LEN", "15")
