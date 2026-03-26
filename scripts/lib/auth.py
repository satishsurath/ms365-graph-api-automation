"""Authentication helpers built on MSAL Python."""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import msal

from .config import AuthSettings
from .session_logging import get_active_session


class AuthError(RuntimeError):
    """Raised when authentication or token acquisition fails."""


@dataclass(frozen=True)
class TokenResult:
    access_token: str
    source: str
    expires_on: int | None
    granted_scopes: tuple[str, ...]
    account_username: str | None
    tenant_id: str | None


class TokenCacheStore:
    """Persist an MSAL serializable token cache on disk."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _locked_handle(self):
        with self.path.open("a+", encoding="utf-8") as handle:
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            except OSError:
                pass

            try:
                yield handle
            finally:
                try:
                    if os.name == "nt":
                        import msvcrt

                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass

    def load(self) -> msal.SerializableTokenCache:
        cache = msal.SerializableTokenCache()
        if not self.path.exists():
            return cache

        with self._locked_handle() as handle:
            handle.seek(0)
            cached_state = handle.read()
            if cached_state:
                cache.deserialize(cached_state)
        return cache

    def save(self, cache: msal.SerializableTokenCache) -> None:
        if not cache.has_state_changed:
            return

        with self._locked_handle() as handle:
            handle.seek(0)
            handle.truncate(0)
            handle.write(cache.serialize())
            handle.flush()
            os.fsync(handle.fileno())


def _format_error(result: dict | None) -> str:
    if not result:
        return "Token acquisition failed with an empty MSAL result."

    error = result.get("error", "unknown_error")
    description = result.get("error_description", "No error description returned.")
    error_codes = {str(code) for code in result.get("error_codes", [])}
    correlation_id = result.get("correlation_id")
    details = [f"Token acquisition failed: {error}", description]

    if "7000218" in error_codes or "AADSTS7000218" in description:
        details.extend(
            [
                "",
                "Likely fix for local delegated scripts:",
                "- Register 'http://localhost' under Authentication -> Mobile and desktop applications.",
                "- Set Authentication -> Advanced settings -> Allow public client flows to Yes.",
                "- Do not rely on a Web redirect URI for this public-client localhost flow.",
            ]
        )

    if correlation_id:
        details.append(f"correlation_id={correlation_id}")
    return "\n".join(details)


def _extract_granted_scopes(result: dict, fallback_scopes: Iterable[str]) -> tuple[str, ...]:
    raw_scope = result.get("scope")
    if isinstance(raw_scope, str) and raw_scope.strip():
        return tuple(raw_scope.split())
    return tuple(fallback_scopes)


def _extract_account_username(result: dict) -> str | None:
    claims = result.get("id_token_claims") or {}
    return claims.get("preferred_username") or claims.get("email")


def _extract_tenant_id(result: dict) -> str | None:
    claims = result.get("id_token_claims") or {}
    return claims.get("tid")


def _summarize_auth_error(result: dict | None, *, debug_enabled: bool) -> dict[str, object]:
    if not result:
        return {"error": "empty_result"}

    summary: dict[str, object] = {
        "error": result.get("error", "unknown_error"),
        "error_codes": result.get("error_codes", []),
        "correlation_id": result.get("correlation_id"),
    }
    if debug_enabled:
        summary["error_description"] = result.get("error_description")
    return summary


def acquire_access_token(
    *,
    settings: AuthSettings,
    scopes: Iterable[str],
    login_hint: str | None = None,
    force_interactive: bool = False,
    launch_message: bool = False,
) -> TokenResult:
    requested_scopes = tuple(scopes)
    if not requested_scopes:
        raise AuthError("No Graph scopes were selected for token acquisition.")

    session = get_active_session()
    if session:
        auth_request_event = {
            "authority": settings.authority,
            "scopes": requested_scopes,
            "login_hint_provided": bool(login_hint),
            "force_interactive": force_interactive,
        }
        if session.debug_enabled:
            auth_request_event["client_id"] = settings.client_id
        session.log_event("auth_token_request", **auth_request_event)

    cache_store = TokenCacheStore(settings.token_cache_path)
    cache = cache_store.load()

    app = msal.PublicClientApplication(
        settings.client_id,
        authority=settings.authority,
        token_cache=cache,
    )

    result: dict | None = None
    source = "interactive"

    if not force_interactive:
        accounts = app.get_accounts(username=login_hint) if login_hint else app.get_accounts()
        if session:
            session.log_event("auth_cache_lookup", cached_account_count=len(accounts))
        for account in accounts:
            result = app.acquire_token_silent(list(requested_scopes), account=account)
            if result and "access_token" in result:
                source = "cache"
                break

    if not result or "access_token" not in result:
        prompt = None if login_hint else "select_account"
        if session:
            session.log_event(
                "auth_interactive_started",
                prompt=prompt or "default",
                redirect_port=settings.redirect_port,
            )
        callback = None
        if launch_message:
            callback = lambda ui="browser", **_: print(  # noqa: E731
                f"Launching {ui} for Microsoft sign-in..."
            )
        result = app.acquire_token_interactive(
            list(requested_scopes),
            prompt=prompt,
            login_hint=login_hint,
            port=settings.redirect_port,
            on_before_launching_ui=callback,
        )
        source = "interactive"

    cache_store.save(cache)

    if not result or "access_token" not in result:
        if session:
            session.log_event(
                "auth_error",
                **_summarize_auth_error(result, debug_enabled=session.debug_enabled),
            )
        raise AuthError(_format_error(result))

    expires_on = result.get("expires_on")
    normalized_expires_on = int(expires_on) if expires_on else None
    token_result = TokenResult(
        access_token=result["access_token"],
        source=source,
        expires_on=normalized_expires_on,
        granted_scopes=_extract_granted_scopes(result, requested_scopes),
        account_username=_extract_account_username(result),
        tenant_id=_extract_tenant_id(result),
    )
    if session:
        auth_acquired_event: dict[str, object] = {
            "source": token_result.source,
            "expires_on": token_result.expires_on,
            "granted_scopes": token_result.granted_scopes,
        }
        if session.debug_enabled:
            auth_acquired_event["account_username"] = token_result.account_username
            auth_acquired_event["tenant_id"] = token_result.tenant_id
        session.log_event("auth_token_acquired", **auth_acquired_event)
    return token_result
