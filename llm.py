"""Minimal OpenAI-compatible chat client (standard library only)."""

import json
import urllib.error
import urllib.request

import config


class LLMError(RuntimeError):
    pass


class ChatClient:
    # 모델 서버 주소와 인증 및 요청 옵션을 설정한다.
    def __init__(
        self,
        base_url: str = config.LLM_BASE_URL,
        model: str = config.LLM_MODEL,
        api_key: str = config.LLM_API_KEY,
        reasoning_effort: str = config.LLM_REASONING_EFFORT,
        timeout: int = config.LLM_TIMEOUT_SEC,
    ):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.api_key = api_key
        self.reasoning_effort = reasoning_effort
        self.timeout = timeout

    # 대화와 도구 명세를 서버에 보내고 모델의 응답 메시지를 반환한다.
    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """Send one chat turn and return the assistant message dict."""
        payload: dict = {"model": self.model, "messages": messages, "temperature": 0}
        if tools:
            payload["tools"] = tools
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request = urllib.request.Request(
            self.url, data=json.dumps(payload).encode("utf-8"), headers=headers
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise LLMError(f"HTTP {e.code} from {self.url}: {detail}") from e
        except urllib.error.URLError as e:
            raise LLMError(f"Cannot reach {self.url}: {e.reason}") from e

        return data["choices"][0]["message"]
