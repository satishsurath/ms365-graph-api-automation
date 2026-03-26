#!/usr/bin/env python3
"""Call Microsoft Graph /me using the cached token flow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lib.auth import AuthError, acquire_access_token
from lib.config import ConfigError, load_settings
from lib.graph import GraphApiError, graph_get_json
from lib.session_logging import clear_active_session, start_session


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Call Microsoft Graph /me using your local .env and token cache.",
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
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the raw Graph response JSON.",
    )
    return parser


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
                "command": "graph_me",
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
            launch_message=not args.json,
        )
        response = graph_get_json(
            access_token=token.access_token,
            path="/me",
            query={"$select": "id,displayName,userPrincipalName,mail"},
        )
    except (ConfigError, AuthError, GraphApiError) as exc:
        if session:
            error_event = {"error_type": type(exc).__name__}
            if session.debug_enabled:
                error_event["error"] = str(exc)
            session.log_event("script_error", **error_event)
            session.finish(status="error")
            clear_active_session(session)
        parser.exit(status=1, message=f"{exc}\n")

    if args.json:
        if session:
            response["_session_log_path"] = str(session.log_path)
        if session:
            session.finish(status="success", token_source=token.source)
            clear_active_session(session)
        print(json.dumps(response, indent=2, sort_keys=True))
        return 0

    print("Graph /me succeeded.")
    print(f"Display name: {response.get('displayName') or 'unknown'}")
    print(f"User principal name: {response.get('userPrincipalName') or 'unknown'}")
    print(f"Mail: {response.get('mail') or 'unknown'}")
    print(f"Object ID: {response.get('id') or 'unknown'}")
    print(f"Session log: {session.log_path if session else 'unknown'}")
    if session:
        session.finish(status="success", token_source=token.source)
        clear_active_session(session)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
