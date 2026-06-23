# 테스트를 결정론적으로 유지하기 위해 LLM 호출을 차단하고 휴리스틱 추출로 폴백시킨다
import os

# 도달 불가능한 호스트로 지정 → LLMClient.available()가 False → 휴리스틱 경로
os.environ.setdefault("OLLAMA_HOST", "http://127.0.0.1:1")
