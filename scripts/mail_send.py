#!/usr/bin/env python3
"""Send a mail message as the signed-in Microsoft 365 user."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lib.auth import AuthError, acquire_access_token
from lib.config import ConfigError, load_settings
from lib.graph import GraphApiError, graph_post_json
from lib.session_logging import clear_active_session, start_session


REQUIRED_SCOPES = ("Mail.Send",)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Send an email as the signed-in Microsoft 365 user.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        help="Optional path to the .env file. Defaults to the repo root .env.",
    )
    parser.add_argument(
        "--to",
        action="append",
        required=True,
        help="Recipient email address. Repeat the flag or use comma-separated values.",
    )
    parser.add_argument(
        "--cc",
        action="append",
        default=[],
        help="CC recipient email address. Repeat the flag or use comma-separated values.",
    )
    parser.add_argument(
        "--bcc",
        action="append",
        default=[],
        help="BCC recipient email address. Repeat the flag or use comma-separated values.",
    )
    parser.add_argument(
        "--subject",
        required=True,
        help="Message subject line.",
    )

    body_group = parser.add_mutually_exclusive_group(required=True)
    body_group.add_argument(
        "--body",
        help="Inline message body content.",
    )
    body_group.add_argument(
        "--body-file",
        type=Path,
        help="Path to a file containing the message body.",
    )

    parser.add_argument(
        "--body-type",
        choices=("text", "html"),
        default="text",
        help="Interpret the body as plain text or HTML. Defaults to text.",
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
        "--dry-run",
        action="store_true",
        help="Build and print the outgoing request without sending it to Microsoft Graph.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print structured JSON output instead of human-readable text.",
    )
    parser.set_defaults(save_to_sent_items=True)
    parser.add_argument(
        "--no-save-to-sent-items",
        dest="save_to_sent_items",
        action="store_false",
        help="Do not save a copy of the message to Sent Items.",
    )
    return parser


def _parse_recipients(raw_values: list[str]) -> list[str]:
    recipients: list[str] = []
    seen: set[str] = set()
    for raw_value in raw_values:
        for value in raw_value.split(","):
            email = value.strip()
            if email and email not in seen:
                recipients.append(email)
                seen.add(email)
    return recipients


def _recipient_objects(addresses: list[str]) -> list[dict[str, dict[str, str]]]:
    return [{"emailAddress": {"address": address}} for address in addresses]


def _load_body(args: argparse.Namespace) -> str:
    if args.body is not None:
        return args.body
    if args.body_file is None:
        raise ValueError("Either --body or --body-file is required.")
    return args.body_file.read_text(encoding="utf-8")


def _build_message_payload(args: argparse.Namespace) -> dict[str, object]:
    to_recipients = _parse_recipients(args.to)
    cc_recipients = _parse_recipients(args.cc)
    bcc_recipients = _parse_recipients(args.bcc)

    if not to_recipients:
        raise ValueError("At least one --to recipient is required.")

    content_type = "HTML" if args.body_type == "html" else "Text"
    payload: dict[str, object] = {
        "message": {
            "subject": args.subject,
            "body": {
                "contentType": content_type,
                "content": _load_body(args),
            },
            "toRecipients": _recipient_objects(to_recipients),
        },
        "saveToSentItems": args.save_to_sent_items,
    }

    message = payload["message"]
    if cc_recipients:
        message["ccRecipients"] = _recipient_objects(cc_recipients)  # type: ignore[index]
    if bcc_recipients:
        message["bccRecipients"] = _recipient_objects(bcc_recipients)  # type: ignore[index]

    return payload


def _json_summary(payload: dict[str, object], dry_run: bool) -> dict[str, object]:
    message = payload["message"]
    return {
        "dry_run": dry_run,
        "required_scopes": list(REQUIRED_SCOPES),
        "save_to_sent_items": payload["saveToSentItems"],
        "subject": message["subject"],
        "to": [item["emailAddress"]["address"] for item in message["toRecipients"]],
        "cc": [item["emailAddress"]["address"] for item in message.get("ccRecipients", [])],
        "bcc": [item["emailAddress"]["address"] for item in message.get("bccRecipients", [])],
        "body_type": message["body"]["contentType"],
        "body_preview": message["body"]["content"][:200],
    }


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    session = None

    try:
        payload = _build_message_payload(args)
        summary = _json_summary(payload, dry_run=args.dry_run)
        if args.dry_run:
            if args.json:
                print(json.dumps(summary, indent=2, sort_keys=True))
            else:
                print("Dry run only. No email was sent.")
                print(f"Subject: {summary['subject']}")
                print(f"To: {', '.join(summary['to'])}")
                if summary["cc"]:
                    print(f"CC: {', '.join(summary['cc'])}")
                if summary["bcc"]:
                    print(f"BCC: {', '.join(summary['bcc'])}")
                print(f"Body type: {summary['body_type']}")
                print(f"Save to Sent Items: {summary['save_to_sent_items']}")
            return 0

        settings = load_settings(args.env_file)
        session = start_session(
            script_name=Path(__file__).name,
            log_dir=settings.session_log_dir,
            debug_enabled=settings.session_log_debug,
            metadata={
                "command": "mail_send",
                "required_scopes": REQUIRED_SCOPES,
                "to_count": len(summary["to"]),
                "cc_count": len(summary["cc"]),
                "bcc_count": len(summary["bcc"]),
                "body_type": args.body_type,
                "save_to_sent_items": args.save_to_sent_items,
                "login_hint_provided": bool(args.login_hint),
                "force_interactive": args.force_interactive,
                **({"subject": args.subject} if settings.session_log_debug else {}),
            },
        )
        token = acquire_access_token(
            settings=settings,
            scopes=REQUIRED_SCOPES,
            login_hint=args.login_hint,
            force_interactive=args.force_interactive,
            launch_message=not args.json,
        )
        graph_post_json(
            access_token=token.access_token,
            path="/me/sendMail",
            json_body=payload,
            expected_statuses=(202,),
        )
    except (ConfigError, AuthError, GraphApiError, OSError, ValueError) as exc:
        if session:
            error_event = {"error_type": type(exc).__name__}
            if session.debug_enabled:
                error_event["error"] = str(exc)
            session.log_event("script_error", **error_event)
            session.finish(status="error")
            clear_active_session(session)
        parser.exit(status=1, message=f"{exc}\n")

    summary["token_source"] = token.source
    summary["session_log_path"] = str(session.log_path) if session else None

    if args.json:
        if session:
            session.finish(status="success", token_source=token.source)
            clear_active_session(session)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    print("Graph mail send accepted.")
    print(f"Subject: {summary['subject']}")
    print(f"To: {', '.join(summary['to'])}")
    if summary["cc"]:
        print(f"CC: {', '.join(summary['cc'])}")
    if summary["bcc"]:
        print(f"BCC: {', '.join(summary['bcc'])}")
    print(f"Save to Sent Items: {summary['save_to_sent_items']}")
    print(f"Token source: {summary['token_source']}")
    print(f"Session log: {summary['session_log_path'] or 'unknown'}")
    if session:
        session.finish(status="success", token_source=token.source)
        clear_active_session(session)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
