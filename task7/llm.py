"""Small DeepSeek adapter. Credentials never enter trace payloads."""
import json
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


class ModelError(RuntimeError):
    pass


class DeepSeek:
    def __init__(self):
        self.key = os.getenv("DEEPSEEK_API_KEY", "")
        self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
        self.base = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
        self.usage = []

    def complete(self, messages, tools=None, json_mode=False):
        if not self.key:
            raise ModelError("尚未配置 DEEPSEEK_API_KEY，请在本机 .env 中设置后重启服务。")
        payload = dict(model=self.model, messages=messages, temperature=0,
                       max_tokens=4500, thinking={"type": "disabled"})
        if tools:
            payload.update(tools=tools, tool_choice="required")
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        # Retry only explicitly transient HTTP failures; a timeout may already be billed.
        for attempt in range(2):
            try:
                response = httpx.post(f"{self.base}/chat/completions", json=payload,
                                      headers={"Authorization": f"Bearer {self.key}"},
                                      timeout=httpx.Timeout(90, connect=15))
            except httpx.TimeoutException as exc:
                raise ModelError("模型请求超时，请稍后重试；本次没有生成行程。") from exc
            except httpx.HTTPError as exc:
                raise ModelError("暂时无法连接模型服务，请检查网络后重试。") from exc
            if response.status_code in (429, 500, 502, 503) and attempt == 0:
                time.sleep(1)
                continue
            if response.status_code != 200:
                labels = {401: "密钥验证失败", 402: "账户余额不足", 429: "请求过于频繁"}
                raise ModelError(f"DeepSeek {labels.get(response.status_code, '服务异常')}（HTTP {response.status_code}）。")
            try:
                data = response.json()
                choice = data["choices"][0]
                if choice.get("finish_reason") == "length":
                    raise ModelError("模型输出超过长度限制，本次结果未采用。请简化需求后重试。")
                self.usage.append(data.get("usage", {}))
                message = choice["message"]
                if not message.get("tool_calls") and not (message.get("content") or "").strip():
                    raise ModelError("模型返回了空结果，请重试。")
                return {k: v for k, v in message.items() if k in ("role", "content", "tool_calls")}
            except (KeyError, ValueError, IndexError) as exc:
                raise ModelError("模型返回格式异常，本次结果未采用。") from exc


def json_content(message):
    try:
        return json.loads(message.get("content") or "")
    except (ValueError, TypeError) as exc:
        raise ModelError("模型未返回有效 JSON，本次结果未采用。") from exc
