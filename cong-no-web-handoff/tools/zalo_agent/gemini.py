"""ZALO-AGENT-01 Phần 4: hỏi Gemini số tiền của ảnh đã che, qua HAI đường (ANH-GEMINI-01 mục 3).

- `gemini-proxy`: proxy 9router dùng Gemini OAuth, địa chỉ từ `ZALO_AGENT_GEMINI_PROXY` (kiểu tương thích OpenAI mặc định,
  `ZALO_AGENT_GEMINI_PROXY_STYLE=gemini` cho kiểu Gemini; khóa tùy chọn `ZALO_AGENT_GEMINI_PROXY_KEY`);
- `gemini-api`: Gemini API trả phí, khóa `GEMINI_API_KEY` (gửi qua header, không nằm trong URL).

Model từ `ZALO_AGENT_GEMINI_MODEL`. `ZALO_AGENT_EXTERNAL` mặc định `off`: tắt thì không có kết nối ra ngoài nào, và thiếu một trong hai
đường hay thiếu model cũng coi như tắt (không đường nào được tự quyết một mình). Mọi cấu hình đọc từ biến môi trường ở máy có Zalo,
không vào repo, không vào log. Lời nhắn là câu cố định, chỉ kèm ảnh đã che. Kết quả là dữ liệu, không bao giờ là lệnh: phải đúng khuôn
JSON `{is_transfer, amount_vnd, txn_time, bank}` (số tiền là số nguyên), sai khuôn là lỗi. Lỗi chỉ là mã ngắn, không bao giờ kèm nội dung
trả về hay khóa. Đoạn gọi mạng duy nhất là `post_json`: đổi nhà cung cấp thì đổi ở đó và ở `request_for`.
"""
from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

PROMPT = ("Đây là ảnh biên lai chuyển khoản ngân hàng đã che thông tin cá nhân. Chỉ trả về MỘT đối tượng JSON, không giải thích, đúng bốn "
          'khóa: {"is_transfer": true hoặc false, "amount_vnd": số tiền chuyển bằng số nguyên đồng (không dấu phân cách) hoặc null, '
          '"txn_time": thời điểm giao dịch dạng ISO 8601 hoặc null, "bank": tên ngân hàng hoặc null}.')
SHAPE = ("is_transfer", "amount_vnd", "txn_time", "bank")
ROUTES = ("gemini-proxy", "gemini-api")
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TIME = re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?")
FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
MODEL = re.compile(r"[A-Za-z0-9._+-]{1,40}")
TIMEOUT = 60


class AskError(Exception):
    """`code` là mã ngắn `[a-z_0-9]{1,30}`: không bao giờ chứa nội dung trả về hay khóa."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Route:
    name: str
    url: str
    headers: tuple
    style: str   # "openai" hoặc "gemini"
    model: str


def post_json(url: str, headers: dict, body: dict, timeout: float = TIMEOUT) -> dict:
    """Điểm duy nhất gọi mạng. Mọi lỗi đổi thành AskError có mã ngắn."""
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read(4_000_000))
    except urllib.error.HTTPError as exc:
        raise AskError(f"http_{exc.code}") from None
    except TimeoutError:
        raise AskError("timeout") from None
    except (urllib.error.URLError, OSError):
        raise AskError("network") from None
    except ValueError:
        raise AskError("bad_shape") from None
    if not isinstance(value, dict):
        raise AskError("bad_shape")
    return value


def request_for(route: Route, image: bytes) -> tuple[str, dict, dict]:
    encoded = base64.b64encode(image).decode()
    if route.style == "openai":
        body = {"model": route.model, "temperature": 0, "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}}]}]}
        return route.url, dict(route.headers), body
    body = {"contents": [{"parts": [{"text": PROMPT}, {"inline_data": {"mime_type": "image/jpeg", "data": encoded}}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}}
    return route.url, dict(route.headers), body


def text_of(route: Route, value: dict) -> str:
    try:
        text = value["choices"][0]["message"]["content"] if route.style == "openai" else value["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        raise AskError("bad_shape") from None
    if not isinstance(text, str):
        raise AskError("bad_shape")
    return text


def parse(text: str) -> dict:
    """Đúng bốn khóa, `is_transfer` là bool, `amount_vnd` là số nguyên (không phải float hay chuỗi) hoặc null, `txn_time` chuỗi ISO hoặc
    null, `bank` chuỗi ngắn hoặc null. Cho phép bọc trong ```json … ```; thừa chữ ngoài JSON là sai khuôn."""
    fenced = FENCE.fullmatch(text.strip())
    try:
        value = json.loads(fenced.group(1) if fenced else text)
    except ValueError:
        raise AskError("bad_shape") from None
    amount, when, bank = (value.get(key) for key in SHAPE[1:]) if isinstance(value, dict) else (None, None, None)
    ok = (isinstance(value, dict) and set(value) == set(SHAPE) and isinstance(value["is_transfer"], bool)
          and (amount is None or (isinstance(amount, int) and not isinstance(amount, bool) and 0 <= amount < 10**13))
          and (when is None or (isinstance(when, str) and TIME.fullmatch(when)))
          and (bank is None or (isinstance(bank, str) and re.fullmatch(r"[\w .&()\-]{1,60}", bank))))
    if not ok:
        raise AskError("bad_shape")
    return {key: value[key] for key in SHAPE}


class Gemini:
    """Cấu hình hai đường từ biến môi trường. `ready` chỉ True khi gửi ra ngoài đang bật VÀ đủ cả hai đường VÀ có model."""

    def __init__(self, env: dict | None = None, post=post_json):
        env = os.environ if env is None else env
        self.post = post
        self.model = (env.get("ZALO_AGENT_GEMINI_MODEL") or "").strip()
        self.routes: dict[str, Route] = {}
        if (env.get("ZALO_AGENT_EXTERNAL") or "off").strip().lower() != "on" or not MODEL.fullmatch(self.model):
            return
        proxy, style, key = (env.get("ZALO_AGENT_GEMINI_PROXY") or "").strip().rstrip("/"), (env.get("ZALO_AGENT_GEMINI_PROXY_STYLE") or "openai").strip(), \
            (env.get("ZALO_AGENT_GEMINI_PROXY_KEY") or "").strip()
        if re.fullmatch(r"https?://\S+", proxy) and style in ("openai", "gemini"):
            url = f"{proxy}/chat/completions" if style == "openai" else f"{proxy}/v1beta/models/{self.model}:generateContent"
            self.routes["gemini-proxy"] = Route("gemini-proxy", url, (("Authorization", f"Bearer {key}"),) if key else (), style, self.model)
        if (env.get("GEMINI_API_KEY") or "").strip():
            self.routes["gemini-api"] = Route("gemini-api", API_URL.format(model=self.model),
                                              (("x-goog-api-key", env["GEMINI_API_KEY"].strip()),), "gemini", self.model)

    @property
    def ready(self) -> bool:
        return set(self.routes) == set(ROUTES)

    def ask(self, name: str, image: bytes) -> dict:
        route = self.routes[name]
        url, headers, body = request_for(route, image)
        return parse(text_of(route, self.post(url, headers, body)))
