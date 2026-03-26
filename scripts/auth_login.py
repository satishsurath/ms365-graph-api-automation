#!/usr/bin/env python3
"""Authenticate interactively and cache a Graph token locally."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from lib.auth import AuthError, acquire_access_token
from lib.config import ConfigError, load_settings
from lib.session_logging import clear_active_session, start_session


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Authenticate against Microsoft Graph using your .env config.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        help="Optional path to the .env file. Defaults to the repo root .env.",
    )
    parser.add_argument(
        "--include-shared",
        action="store_true",
        help="Include the MSFT_GRAPH_SCOPES_SHARED bundle in the token request.",
    )
    parser.add_argument(
        "--include-collab",
        action="store_true",
        help="Include the MSFT_GRAPH_SCOPES_COLLAB bundle in the token request.",
    )
    parser.add_argument(
        "--scope",
        action="append",
        default=[],
        help="Append an extra delegated Graph scope. Repeat as needed.",
    )
    parser.add_argument(
        "--login-hint",
        help="Optional UPN/email hint to prefill the interactive sign-in flow.",
    )
    parser.add_argument(
        "--force-interactive",
        action="store_true",
        help="Skip cache lookup and force a fresh browser sign-in.",
    )

    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--json",
        action="store_true",
        help="Print a JSON summary instead of human-readable output.",
    )
    output_group.add_argument(
        "--print-access-token",
        action="store_true",
        help="Print only the access token to stdout.",
    )
    return parser


def to_iso8601(epoch_seconds: int | None) -> str | None:
    if not epoch_seconds:
        return None
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).isoformat()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    session = None

    try:
        settings = load_settings(args.env_file)
        scopes = settings.selected_graph_scopes(
            include_shared=args.include_shared,
            include_collab=args.include_collab,
            extra_scopes=args.scope,
        )
        session = start_session(
            script_name=Path(__file__).name,
            log_dir=settings.session_log_dir,
            debug_enabled=settings.session_log_debug,
            metadata={
                "command": "auth_login",
                "scope_count": len(scopes),
                "requested_scopes": scopes,
                "include_shared": args.include_shared,
                "include_collab": args.include_collab,
                "login_hint_provided": bool(args.login_hint),
                "force_interactive": args.force_interactive,
            },
        )
        token = acquire_access_token(
            settings=settings,
            scopes=scopes,
            login_hint=args.login_hint,
            force_interactive=args.force_interactive,
            launch_message=not (args.json or args.print_access_token),
        )
    except (ConfigError, AuthError) as exc:
        if session:
            error_event = {"error_type": type(exc).__name__}
            if session.debug_enabled:
                error_event["error"] = str(exc)
            session.log_event("script_error", **error_event)
            session.finish(status="error")
            clear_active_session(session)
        parser.exit(status=1, message=f"{exc}\n")

    if args.print_access_token:
        if session:
            session.finish(status="success", token_source=token.source)
            clear_active_session(session)
        print(token.access_token)
        return 0

    payload = {
        "account": token.account_username,
        "tenant_id": token.tenant_id,
        "authority": settings.authority,
        "cache_path": str(settings.token_cache_path),
        "session_log_path": str(session.log_path) if session else None,
        "token_source": token.source,
        "expires_at": to_iso8601(token.expires_on),
        "requested_scopes": list(scopes),
        "granted_scopes": list(token.granted_scopes),
    }

    if args.json:
        if session:
            session.finish(status="success", token_source=token.source)
            clear_active_session(session)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print("Authentication succeeded.")
    print(f"Account: {token.account_username or 'unknown'}")
    print(f"Tenant ID: {token.tenant_id or 'unknown'}")
    print(f"Authority: {settings.authority}")
    print(f"Token source: {token.source}")
    print(f"Expires at (UTC): {payload['expires_at'] or 'unknown'}")
    print(f"Cache path: {settings.token_cache_path}")
    print(f"Session log: {payload['session_log_path'] or 'unknown'}")
    print("Granted scopes:")
    for scope in token.granted_scopes:
        print(f"  - {scope}")
    if session:
        session.finish(status="success", token_source=token.source)
        clear_active_session(session)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
