"""Encrypted local artifact storage for Microsoft Graph payloads."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import base64
import hashlib
import json
import os
import sqlite3
import uuid

import keyring
from keyring.errors import KeyringError, NoKeyringError
from nacl.exceptions import CryptoError
from nacl.secret import Aead
from nacl.utils import random


SCHEMA_VERSION = 1


class StoreError(RuntimeError):
    """Raised when the local encrypted artifact store cannot be used."""


@dataclass(frozen=True)
class StoreStatus:
    store_dir: Path
    index_path: Path
    artifacts_dir: Path
    schema_version: int
    artifact_count: int
    keyring_service: str
    keyring_account: str
    master_key_status: str


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    artifact_type: str
    account_fingerprint: str
    content_type: str
    ciphertext_path: Path
    plaintext_sha256: str
    plaintext_size: int
    metadata: dict[str, Any]
    created_at: str
    updated_at: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


def build_account_fingerprint(*parts: str) -> str:
    normalized = [part.strip() for part in parts if part and part.strip()]
    if not normalized:
        raise ValueError("At least one stable identity component is required.")
    joined = "\x1f".join(normalized).encode("utf-8")
    return hashlib.sha256(joined).hexdigest()


class GraphArtifactStore:
    """Store encrypted Graph artifacts on disk with a SQLite index."""

    def __init__(self, *, store_dir: Path, keyring_service: str) -> None:
        self.store_dir = Path(store_dir).expanduser().resolve()
        self.index_path = self.store_dir / "index.sqlite3"
        self.artifacts_dir = self.store_dir / "artifacts"
        self.keyring_service = keyring_service.strip() or "ms365-graph-api-automation"
        store_hash = hashlib.sha256(str(self.store_dir).encode("utf-8")).hexdigest()[:24]
        self.keyring_account = f"graph-store-master-key:{store_hash}"

    def initialize(self) -> StoreStatus:
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._initialize_index()
        key_created = self._ensure_master_key()
        return self.status(master_key_status="created" if key_created else "loaded")

    def status(self, *, master_key_status: str | None = None) -> StoreStatus:
        self._initialize_index()
        schema_version = self._read_schema_version()
        artifact_count = self._count_artifacts()
        return StoreStatus(
            store_dir=self.store_dir,
            index_path=self.index_path,
            artifacts_dir=self.artifacts_dir,
            schema_version=schema_version,
            artifact_count=artifact_count,
            keyring_service=self.keyring_service,
            keyring_account=self.keyring_account,
            master_key_status=master_key_status or self._master_key_status(),
        )

    def put_bytes(
        self,
        *,
        artifact_type: str,
        account_fingerprint: str,
        payload: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactRecord:
        if not artifact_type.strip():
            raise StoreError("artifact_type must be non-empty.")
        if not account_fingerprint.strip():
            raise StoreError("account_fingerprint must be non-empty.")

        self.initialize()
        artifact_id = uuid.uuid4().hex
        now = _utc_now()
        metadata_dict = dict(metadata or {})
        plaintext_sha256 = hashlib.sha256(payload).hexdigest()

        artifact_key = random(Aead.KEY_SIZE)
        artifact_box = Aead(artifact_key)
        payload_aad = self._payload_aad(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            account_fingerprint=account_fingerprint,
        )
        ciphertext = bytes(artifact_box.encrypt(payload, payload_aad))

        master_key = self._load_master_key()
        master_box = Aead(master_key)
        wrapped_key = bytes(
            master_box.encrypt(
                artifact_key,
                self._wrapped_key_aad(artifact_id=artifact_id, artifact_type=artifact_type),
            )
        )

        relative_path = Path("artifacts") / artifact_id[:2] / f"{artifact_id}.bin"
        absolute_path = self.store_dir / relative_path
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(absolute_path, ciphertext)

        try:
            with self._connection() as conn:
                conn.execute(
                    """
                    INSERT INTO artifacts (
                        artifact_id,
                        artifact_type,
                        account_fingerprint,
                        content_type,
                        ciphertext_path,
                        wrapped_key,
                        plaintext_sha256,
                        plaintext_size,
                        metadata_json,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        artifact_id,
                        artifact_type,
                        account_fingerprint,
                        content_type,
                        str(relative_path),
                        sqlite3.Binary(wrapped_key),
                        plaintext_sha256,
                        len(payload),
                        json.dumps(metadata_dict, separators=(",", ":"), sort_keys=True),
                        now,
                        now,
                    ),
                )
        except sqlite3.Error as exc:
            absolute_path.unlink(missing_ok=True)
            raise StoreError(f"Could not write the index row for artifact {artifact_id}.") from exc

        return ArtifactRecord(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            account_fingerprint=account_fingerprint,
            content_type=content_type,
            ciphertext_path=absolute_path,
            plaintext_sha256=plaintext_sha256,
            plaintext_size=len(payload),
            metadata=metadata_dict,
            created_at=now,
            updated_at=now,
        )

    def put_json(
        self,
        *,
        artifact_type: str,
        account_fingerprint: str,
        value: dict[str, Any] | list[Any],
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactRecord:
        payload = json.dumps(value, indent=2, sort_keys=True).encode("utf-8")
        return self.put_bytes(
            artifact_type=artifact_type,
            account_fingerprint=account_fingerprint,
            payload=payload,
            content_type="application/json",
            metadata=metadata,
        )

    def get_bytes(self, artifact_id: str) -> bytes:
        row = self._get_artifact_row(artifact_id)
        ciphertext_path = self.store_dir / row["ciphertext_path"]
        try:
            ciphertext = ciphertext_path.read_bytes()
        except OSError as exc:
            raise StoreError(f"Could not read ciphertext for artifact {artifact_id}.") from exc

        master_key = self._load_master_key()
        master_box = Aead(master_key)
        try:
            artifact_key = master_box.decrypt(
                bytes(row["wrapped_key"]),
                self._wrapped_key_aad(
                    artifact_id=row["artifact_id"],
                    artifact_type=row["artifact_type"],
                ),
            )
        except CryptoError as exc:
            raise StoreError(f"Could not unwrap the key for artifact {artifact_id}.") from exc

        artifact_box = Aead(artifact_key)
        try:
            plaintext = artifact_box.decrypt(
                ciphertext,
                self._payload_aad(
                    artifact_id=row["artifact_id"],
                    artifact_type=row["artifact_type"],
                    account_fingerprint=row["account_fingerprint"],
                ),
            )
        except CryptoError as exc:
            raise StoreError(f"Could not decrypt artifact {artifact_id}.") from exc

        digest = hashlib.sha256(plaintext).hexdigest()
        if digest != row["plaintext_sha256"]:
            raise StoreError(f"Integrity check failed for artifact {artifact_id}.")
        return plaintext

    def get_json(self, artifact_id: str) -> Any:
        payload = self.get_bytes(artifact_id)
        try:
            return json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StoreError(f"Artifact {artifact_id} is not valid JSON.") from exc

    def list_artifacts(self, *, limit: int = 50) -> list[ArtifactRecord]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    artifact_id,
                    artifact_type,
                    account_fingerprint,
                    content_type,
                    ciphertext_path,
                    plaintext_sha256,
                    plaintext_size,
                    metadata_json,
                    created_at,
                    updated_at
                FROM artifacts
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        self.store_dir.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.index_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize_index(self) -> None:
        with self._connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS store_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    artifact_type TEXT NOT NULL,
                    account_fingerprint TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    ciphertext_path TEXT NOT NULL UNIQUE,
                    wrapped_key BLOB NOT NULL,
                    plaintext_sha256 TEXT NOT NULL,
                    plaintext_size INTEGER NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_artifacts_created_at
                ON artifacts(created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_artifacts_account_type
                ON artifacts(account_fingerprint, artifact_type);
                """
            )
            conn.execute(
                "INSERT OR IGNORE INTO store_metadata(key, value) VALUES (?, ?)",
                ("schema_version", str(SCHEMA_VERSION)),
            )
            conn.execute(
                "INSERT OR IGNORE INTO store_metadata(key, value) VALUES (?, ?)",
                ("created_at", _utc_now()),
            )

            current_schema_version = self._read_schema_version(conn)
            if current_schema_version != SCHEMA_VERSION:
                raise StoreError(
                    "Unsupported graph store schema version. "
                    f"Expected {SCHEMA_VERSION}, found {current_schema_version}."
                )

    def _read_schema_version(self, conn: sqlite3.Connection | None = None) -> int:
        owns_connection = conn is None
        connection = conn or self._connect()
        try:
            row = connection.execute(
                "SELECT value FROM store_metadata WHERE key = ?",
                ("schema_version",),
            ).fetchone()
            if not row:
                raise StoreError("Graph store metadata is missing schema_version.")
            return int(row["value"])
        finally:
            if owns_connection:
                connection.close()

    def _count_artifacts(self) -> int:
        with self._connection() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM artifacts").fetchone()
        return int(row["count"]) if row else 0

    def _master_key_status(self) -> str:
        try:
            existing = keyring.get_password(self.keyring_service, self.keyring_account)
        except NoKeyringError as exc:
            raise StoreError(
                "No OS keyring backend is available. Install or configure a supported "
                "keyring backend before using the encrypted graph store."
            ) from exc
        except KeyringError as exc:
            raise StoreError("Could not read the graph store key from the OS keyring.") from exc
        return "loaded" if existing else "missing"

    def _ensure_master_key(self) -> bool:
        try:
            existing = keyring.get_password(self.keyring_service, self.keyring_account)
        except NoKeyringError as exc:
            raise StoreError(
                "No OS keyring backend is available. Install or configure a supported "
                "keyring backend before using the encrypted graph store."
            ) from exc
        except KeyringError as exc:
            raise StoreError("Could not read the graph store key from the OS keyring.") from exc

        if existing:
            return False

        encoded = base64.urlsafe_b64encode(random(Aead.KEY_SIZE)).decode("ascii")
        try:
            keyring.set_password(self.keyring_service, self.keyring_account, encoded)
        except NoKeyringError as exc:
            raise StoreError(
                "No OS keyring backend is available. Install or configure a supported "
                "keyring backend before using the encrypted graph store."
            ) from exc
        except KeyringError as exc:
            raise StoreError("Could not create the graph store key in the OS keyring.") from exc
        return True

    def _load_master_key(self) -> bytes:
        try:
            encoded = keyring.get_password(self.keyring_service, self.keyring_account)
        except NoKeyringError as exc:
            raise StoreError(
                "No OS keyring backend is available. Install or configure a supported "
                "keyring backend before using the encrypted graph store."
            ) from exc
        except KeyringError as exc:
            raise StoreError("Could not read the graph store key from the OS keyring.") from exc
        if not encoded:
            raise StoreError(
                "The graph store key is missing from the OS keyring. "
                "Run scripts/store_init.py first."
            )
        try:
            key = base64.urlsafe_b64decode(encoded.encode("ascii"))
        except ValueError as exc:
            raise StoreError("The graph store key stored in the OS keyring is invalid.") from exc
        if len(key) != Aead.KEY_SIZE:
            raise StoreError("The graph store key stored in the OS keyring has an invalid length.")
        return key

    def _payload_aad(
        self,
        *,
        artifact_id: str,
        artifact_type: str,
        account_fingerprint: str,
    ) -> bytes:
        return _canonical_json(
            {
                "schema_version": SCHEMA_VERSION,
                "scope": "artifact_payload",
                "artifact_id": artifact_id,
                "artifact_type": artifact_type,
                "account_fingerprint": account_fingerprint,
            }
        )

    def _wrapped_key_aad(self, *, artifact_id: str, artifact_type: str) -> bytes:
        return _canonical_json(
            {
                "schema_version": SCHEMA_VERSION,
                "scope": "artifact_key",
                "artifact_id": artifact_id,
                "artifact_type": artifact_type,
            }
        )

    def _atomic_write(self, path: Path, data: bytes) -> None:
        temp_path = path.with_name(f"{path.name}.tmp-{uuid.uuid4().hex}")
        try:
            with temp_path.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
        except OSError as exc:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise StoreError(f"Could not write ciphertext file {path}.") from exc

    def _get_artifact_row(self, artifact_id: str) -> sqlite3.Row:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT
                    artifact_id,
                    artifact_type,
                    account_fingerprint,
                    content_type,
                    ciphertext_path,
                    wrapped_key,
                    plaintext_sha256,
                    plaintext_size,
                    metadata_json,
                    created_at,
                    updated_at
                FROM artifacts
                WHERE artifact_id = ?
                """,
                (artifact_id,),
            ).fetchone()
        if not row:
            raise StoreError(f"Artifact {artifact_id} was not found.")
        return row

    def _record_from_row(self, row: sqlite3.Row) -> ArtifactRecord:
        metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        return ArtifactRecord(
            artifact_id=row["artifact_id"],
            artifact_type=row["artifact_type"],
            account_fingerprint=row["account_fingerprint"],
            content_type=row["content_type"],
            ciphertext_path=self.store_dir / row["ciphertext_path"],
            plaintext_sha256=row["plaintext_sha256"],
            plaintext_size=row["plaintext_size"],
            metadata=metadata,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
