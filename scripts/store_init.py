#!/usr/bin/env python3
"""Initialize or inspect the local encrypted Graph artifact store."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lib.config import ConfigError, load_settings
from lib.storage import GraphArtifactStore, StoreError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Initialize the local encrypted Graph artifact store.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        help="Optional path to the .env file. Defaults to the repo root .env.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a JSON summary instead of human-readable output.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        settings = load_settings(args.env_file)
        store = GraphArtifactStore(
            store_dir=settings.graph_store_dir,
            keyring_service=settings.graph_store_keyring_service,
        )
        status = store.initialize()
    except (ConfigError, StoreError) as exc:
        parser.exit(status=1, message=f"{exc}\n")

    payload = {
        "store_dir": str(status.store_dir),
        "index_path": str(status.index_path),
        "artifacts_dir": str(status.artifacts_dir),
        "schema_version": status.schema_version,
        "artifact_count": status.artifact_count,
        "keyring_service": status.keyring_service,
        "keyring_account": status.keyring_account,
        "master_key_status": status.master_key_status,
    }

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print("Encrypted graph artifact store is ready.")
    print(f"Store directory: {status.store_dir}")
    print(f"SQLite index: {status.index_path}")
    print(f"Artifact directory: {status.artifacts_dir}")
    print(f"Schema version: {status.schema_version}")
    print(f"Artifact count: {status.artifact_count}")
    print(f"Keyring service: {status.keyring_service}")
    print(f"Keyring account: {status.keyring_account}")
    print(f"Master key status: {status.master_key_status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
