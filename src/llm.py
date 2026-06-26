# Ollama LLM 호출을 래핑하고 미가용 시 결정론적 mock으로 폴백하는 클라이언트
import json
import re

from .config import config


class LLMClient:
    def __init__(self, cfg=config):
        self.cfg = cfg
        self._available = None

    def available(self) -> bool:
        # Ollama 서버 연결 가능 여부를 1회 캐시
        if self._available is not None:
            return self._available
        try:
            import requests

            r = requests.get(f"{self.cfg.ollama_host}/api/tags", timeout=2)
            self._available = r.status_code == 200
        except Exception:
            self._available = False
        return self._available

    def generate(self, prompt: str, system: str = "", timeout: float = None) -> str:
        # 실제 Ollama 호출, 실패 시 mock 응답. timeout 미지정 시 기본 120초.
        if self.available():
            try:
                import requests

                r = requests.post(
                    f"{self.cfg.ollama_host}/api/generate",
                    json={
                        "model": self.cfg.ollama_model,
                        "prompt": prompt,
                        "system": system,
                        "stream": False,
                    },
                    timeout=timeout or 120,
                )
                return r.json().get("response", "")
            except Exception:
                pass
        return self._mock(prompt, system)

    def generate_json(self, prompt: str, system: str = "", timeout: float = None) -> dict:
        # JSON 응답을 파싱. 실패 시 본문에서 첫 JSON 블록 추출
        raw = self.generate(prompt + "\n\nJSON으로만 응답하라.", system, timeout=timeout)
        return _extract_json(raw)

    def _mock(self, prompt: str, system: str) -> str:
        # 결정론적 mock — 실제 LLM 없이도 파이프라인·테스트가 동작하도록
        return json.dumps({"_mock": True, "echo": prompt[:80]}, ensure_ascii=False)


def _extract_json(text: str):
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    return {}
