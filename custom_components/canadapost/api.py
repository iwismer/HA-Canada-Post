"""Async API client for Canada Post My Mail (Mon Courrier).

Handles OAuth2 token login, automatic refresh-token rotation, token revocation,
read-only topic ID extraction from the ID token JWT, and fetching My Mail
notifications. Passwords are used once during login/reauth and never stored.
"""

from __future__ import annotations

import base64
from collections.abc import Awaitable, Callable
from datetime import datetime
import json
import logging
import re
import time
from typing import Any

import aiohttp

from .const import (
    CLIENT_ID,
    CONF_ACCESS_TOKEN,
    CONF_EXPIRES_AT,
    CONF_ID_TOKEN,
    CONF_REFRESH_TOKEN,
    DEFAULT_DAY_SPAN,
    OAUTH_SCOPE,
    TOKEN_REFRESH_MARGIN_SECONDS,
    URL_AUTH,
    URL_MAIL,
    URL_REVOKE,
)

_LOGGER = logging.getLogger(__name__)

TokenCallback = Callable[[dict[str, Any]], Awaitable[None]]

_SECOND_FACTOR_RE = re.compile(
    r"(?<![a-z0-9])(verification|two[-_ ]?step|2sv|mfa|otp|security[-_ ]?question)(?![a-z0-9])"
)


class CanadaPostApiError(Exception):
    """Unexpected API failure without exposing sensitive payload bodies."""

    def __init__(self, detail: str, *, status_code: int | None = None) -> None:
        super().__init__(detail)
        self.status_code = status_code


class CanadaPostAuthError(CanadaPostApiError):
    """Credentials were rejected during sign-in."""


class CanadaPostTwoStepRequired(CanadaPostApiError):
    """The account requires two-step verification (unsupported)."""


class CanadaPostReauthRequired(CanadaPostApiError):
    """Stored tokens cannot be refreshed; user must sign in again."""


def extract_topic_id(id_token: str) -> str | None:
    """Extract the My Mail topic_id from the id_token JWT ``sub`` claim."""
    parts = id_token.split(".")
    if len(parts) < 2:
        return None
    payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    sub = claims.get("sub")
    return str(sub) if isinstance(sub, str) and sub else None


def _looks_like_second_factor(payload: Any) -> bool:
    if payload is None:
        return False
    text = json.dumps(payload, default=str).lower()
    return _SECOND_FACTOR_RE.search(text) is not None


async def async_revoke_token(
    session: aiohttp.ClientSession, refresh_token: str
) -> None:
    """Best-effort revoke a refresh token at Canada Post."""
    try:
        async with session.post(
            URL_REVOKE,
            data={
                "token": refresh_token,
                "token_type_hint": "refresh_token",
                "client_id": CLIENT_ID,
            },
        ) as resp:
            if resp.status != 200:
                raise CanadaPostApiError("token revoke refused", status_code=resp.status)
    except (aiohttp.ClientError, TimeoutError) as err:
        raise CanadaPostApiError("token revoke unreachable") from err


class CanadaPostAPI:
    """Async client for Canada Post OAuth2 + My Mail API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        access_token: str | None = None,
        refresh_token: str | None = None,
        id_token: str | None = None,
        expires_at: float | None = None,
        token_callback: TokenCallback | None = None,
    ) -> None:
        self._session = session
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._id_token = id_token
        self._expires_at = expires_at
        self._token_callback = token_callback

    def _token_bundle(self) -> dict[str, Any]:
        return {
            CONF_ACCESS_TOKEN: self._access_token,
            CONF_REFRESH_TOKEN: self._refresh_token,
            CONF_ID_TOKEN: self._id_token,
            CONF_EXPIRES_AT: self._expires_at,
        }

    def _adopt_tokens(self, payload: dict[str, Any]) -> None:
        self._access_token = payload["access_token"]
        self._id_token = payload["id_token"]
        self._refresh_token = payload.get("refresh_token") or self._refresh_token
        expires_in = payload.get("expires_in")
        try:
            self._expires_at = (
                None if expires_in is None else time.time() + float(expires_in)
            )
        except (TypeError, ValueError):
            self._expires_at = None

    async def _post_token(self, form: dict[str, str]) -> tuple[int, Any]:
        try:
            async with self._session.post(
                URL_AUTH,
                data={**form, "client_id": CLIENT_ID, "scope": OAUTH_SCOPE},
            ) as resp:
                try:
                    body = await resp.json(content_type=None)
                except ValueError:
                    body = None
                return resp.status, body
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CanadaPostApiError("sign-in service unreachable") from err

    async def async_login(self, username: str, password: str) -> dict[str, Any]:
        """Authenticate once with username/password and return token bundle."""
        status, body = await self._post_token(
            {"grant_type": "password", "username": username, "password": password}
        )
        if isinstance(body, dict) and body.get("access_token") and body.get("id_token"):
            self._adopt_tokens(body)
            return self._token_bundle()
        if _looks_like_second_factor(body):
            raise CanadaPostTwoStepRequired("two-step verification required")
        if status in (400, 401, 403):
            raise CanadaPostAuthError("invalid credentials", status_code=status)
        raise CanadaPostApiError("sign-in request failed", status_code=status)

    async def async_refresh(self) -> dict[str, Any]:
        """Refresh tokens using the stored refresh_token and persist them."""
        if not self._refresh_token:
            raise CanadaPostReauthRequired("no refresh token available")
        status, body = await self._post_token(
            {"grant_type": "refresh_token", "refresh_token": self._refresh_token}
        )
        if (
            status >= 500
            or status == 429
            or (status != 200 and not isinstance(body, dict))
        ):
            raise CanadaPostApiError("token refresh failed", status_code=status)
        if status != 200 or not isinstance(body, dict):
            raise CanadaPostReauthRequired("token refresh rejected", status_code=status)
        if not body.get("access_token") or not body.get("id_token"):
            raise CanadaPostReauthRequired("token refresh returned incomplete tokens")
        self._adopt_tokens(body)
        if self._token_callback is not None:
            await self._token_callback(self._token_bundle())
        return self._token_bundle()

    async def _ensure_fresh_tokens(self) -> None:
        if not self._access_token or not self._id_token:
            await self.async_refresh()
            return
        if (
            self._expires_at is not None
            and time.time() >= self._expires_at - TOKEN_REFRESH_MARGIN_SECONDS
        ):
            await self.async_refresh()

    async def _request_mail(
        self, topic_id: str, start_date: str, day_span: int
    ) -> tuple[int, Any]:
        url = URL_MAIL.format(topic_id=topic_id)
        params = {"startDate": start_date, "daySpan": str(day_span)}
        headers = {
            "Authorization": f"Bearer {self._access_token}.{self._id_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "okhttp/5.0.0-alpha.11",
        }
        try:
            async with self._session.get(url, headers=headers, params=params) as resp:
                if resp.status == 200:
                    try:
                        return 200, await resp.json(content_type=None)
                    except ValueError as err:
                        raise CanadaPostApiError("unparseable mail response") from err
                return resp.status, None
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CanadaPostApiError("mail service unreachable") from err

    async def async_get_mail(
        self,
        topic_id: str,
        *,
        start_date: str | None = None,
        day_span: int = DEFAULT_DAY_SPAN,
    ) -> dict[str, Any]:
        """Fetch My Mail notifications, refreshing tokens automatically on 401."""
        await self._ensure_fresh_tokens()
        date_str = start_date or datetime.now().strftime("%Y%m%d")

        status, body = await self._request_mail(topic_id, date_str, day_span)
        if status == 401:
            await self.async_refresh()
            status, body = await self._request_mail(topic_id, date_str, day_span)
            if status == 401:
                raise CanadaPostReauthRequired(
                    "mail endpoint rejected refreshed token", status_code=401
                )

        if status != 200 or not isinstance(body, dict):
            raise CanadaPostApiError(
                f"mail request failed with HTTP {status}", status_code=status
            )
        return body
