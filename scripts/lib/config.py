"""Load and validate repository auth settings from .env."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse
import os

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = REPO_ROOT / ".env"
DEFAULT_GRAPH_STORE_DIR = REPO_ROOT / ".graph_store"
DEFAULT_SESSION_LOG_DIR = REPO_ROOT / ".session_logs"
DEFAULT_GRAPH_STORE_KEYRING_SERVICE = "ms365-graph-api-automation"


def _split_scopes(raw_value: str | None) -> tuple[str, ...]:
    if not raw_value:
        return ()

    scopes: list[str] = []
    seen: set[str] = set()
    for scope in raw_value.replace(",", " ").split():
        if scope and scope not in seen:
            scopes.append(scope)
            seen.add(scope)
    return tuple(scopes)


def _parse_bool(raw_value: str | None, *, default: bool = False) -> bool:
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(
            f"Missing required environment variable: {name}. "
            "Check your .env file and Docs/entra-app-setup.md."
        )
    return value


def _resolve_authority(tenant_id: str, authority: str | None) -> str:
    explicit_authority = (authority or "").strip()
    if explicit_authority:
        return explicit_authority.rstrip("/")
    return f"https://login.microsoftonline.com/{tenant_id}"


def _validate_redirect_uri(redirect_uri: str) -> int | None:
    parsed = urlparse(redirect_uri)
    if parsed.scheme != "http" or parsed.hostname != "localhost":
        raise ConfigError(
            "MSFT_REDIRECT_URI must be a localhost HTTP redirect, such as "
            "'http://localhost' or 'http://localhost:8400'."
        )

    path = parsed.path or ""
    if path not in ("", "/"):
        raise ConfigError(
            "Only root-path localhost redirect URIs are supported by these starter scripts. "
            "Use 'http://localhost' or 'http://localhost:<port>'."
        )

    if parsed.params or parsed.query or parsed.fragment:
        raise ConfigError(
            "MSFT_REDIRECT_URI must not include params, query strings, or fragments."
        )

    return parsed.port


def _resolve_cache_path(raw_path: str) -> Path:
    cache_path = Path(raw_path).expanduser()
    if cache_path.is_absolute():
        return cache_path
    return (REPO_ROOT / cache_path).resolve()


@dataclass(frozen=True)
class AuthSettings:
    env_file: Path
    tenant_id: str
    client_id: str
    authority: str
    redirect_uri: str
    redirect_port: int | None
    oidc_scopes: tuple[str, ...]
    graph_scopes: tuple[str, ...]
    shared_scopes: tuple[str, ...]
    collab_scopes: tuple[str, ...]
    token_cache_path: Path
    session_log_dir: Path
    session_log_debug: bool
    graph_store_dir: Path
    graph_store_keyring_service: str

    def selected_graph_scopes(
        self,
        *,
        include_shared: bool = False,
        include_collab: bool = False,
        extra_scopes: Iterable[str] = (),
    ) -> tuple[str, ...]:
        ordered_scopes: list[str] = []
        seen: set[str] = set()

        def add(scopes: Iterable[str]) -> None:
            for scope in scopes:
                cleaned = scope.strip()
                if cleaned and cleaned not in seen:
                    ordered_scopes.append(cleaned)
                    seen.add(cleaned)

        add(self.graph_scopes)
        if include_shared:
            add(self.shared_scopes)
        if include_collab:
            add(self.collab_scopes)
        add(extra_scopes)
        return tuple(ordered_scopes)


def load_settings(env_file: Path | None = None) -> AuthSettings:
    resolved_env_file = (env_file or DEFAULT_ENV_FILE).expanduser().resolve()
    if not resolved_env_file.exists():
        raise ConfigError(
            f"Could not find .env file at {resolved_env_file}. "
            "Create it from .env.example first."
        )

    load_dotenv(resolved_env_file, override=False)

    tenant_id = _require_env("MSFT_TENANT_ID")
    client_id = _require_env("MSFT_CLIENT_ID")
    redirect_uri = _require_env("MSFT_REDIRECT_URI")
    token_cache_path = _require_env("MSFT_TOKEN_CACHE_PATH")
    authority = _resolve_authority(tenant_id, os.getenv("MSFT_AUTHORITY"))
    redirect_port = _validate_redirect_uri(redirect_uri)

    return AuthSettings(
        env_file=resolved_env_file,
        tenant_id=tenant_id,
        client_id=client_id,
        authority=authority,
        redirect_uri=redirect_uri,
        redirect_port=redirect_port,
        oidc_scopes=_split_scopes(os.getenv("MSFT_OIDC_SCOPES")),
        graph_scopes=_split_scopes(os.getenv("MSFT_GRAPH_SCOPES")),
        shared_scopes=_split_scopes(os.getenv("MSFT_GRAPH_SCOPES_SHARED")),
        collab_scopes=_split_scopes(os.getenv("MSFT_GRAPH_SCOPES_COLLAB")),
        token_cache_path=_resolve_cache_path(token_cache_path),
        session_log_dir=_resolve_cache_path(
            os.getenv("MSFT_SESSION_LOG_DIR", str(DEFAULT_SESSION_LOG_DIR))
        ),
        session_log_debug=_parse_bool(os.getenv("MSFT_SESSION_LOG_DEBUG"), default=False),
        graph_store_dir=_resolve_cache_path(
            os.getenv("MSFT_GRAPH_STORE_DIR", str(DEFAULT_GRAPH_STORE_DIR))
        ),
        graph_store_keyring_service=(
            os.getenv(
                "MSFT_GRAPH_STORE_KEYRING_SERVICE",
                DEFAULT_GRAPH_STORE_KEYRING_SERVICE,
            ).strip()
            or DEFAULT_GRAPH_STORE_KEYRING_SERVICE
        ),
    )
