"""Cổng HTTP sang Google cho đăng nhập OAuth.

Mọi lỗi mạng/HTTP đều bị nuốt thành `None` kèm một dòng log: Google nằm ngoài
tầm kiểm soát, và một lần timeout của họ không được biến cú chuyển hướng của
khách thành HTTP 500 — application đọc `None` rồi đưa khách về màn đăng nhập.
Thân câu trả lời KHÔNG vào log: token response chứa credential.
"""

import logging
from typing import Any, Final

import httpx

logger = logging.getLogger(__name__)

GOOGLE_TOKEN_URL: Final[str] = "https://oauth2.googleapis.com/token"
GOOGLE_TOKENINFO_URL: Final[str] = "https://oauth2.googleapis.com/tokeninfo"

#: Khách đang đứng giữa một cú chuyển hướng; quá 10 giây thì thà trả họ về màn
#: đăng nhập với thông báo rõ ràng còn hơn treo tab trắng.
REQUEST_TIMEOUT_SECONDS: Final[float] = 10.0


class HttpxGoogleIdentityGateway:
    """`GoogleIdentityGateway` chạy bằng httpx thật."""

    def __init__(self, *, client_id: str, client_secret: str, redirect_url: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_url = redirect_url

    async def exchange_code(self, code: str) -> dict[str, Any] | None:
        payload = {
            "code": code,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "redirect_uri": self._redirect_url,
            "grant_type": "authorization_code",
        }
        return await self._request("POST", GOOGLE_TOKEN_URL, data=payload)

    async def fetch_tokeninfo(self, id_token: str) -> dict[str, Any] | None:
        return await self._request("GET", GOOGLE_TOKENINFO_URL, params={"id_token": id_token})

    async def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any] | None:
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.request(method, url, **kwargs)
        except httpx.HTTPError as error:
            logger.warning("goi google oauth that bai (%s): %s", url, type(error).__name__)
            return None
        if response.status_code != httpx.codes.OK:
            logger.warning("google oauth tra %s cho %s", response.status_code, url)
            return None
        try:
            parsed = response.json()
        except ValueError:
            logger.warning("google oauth tra body khong phai json cho %s", url)
            return None
        return parsed if isinstance(parsed, dict) else None
