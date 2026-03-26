# Encrypted Artifact Store

This repo now includes a starter local store for encrypted Microsoft Graph artifacts.

The current implementation follows the repo ADR:

- SQLite index for operational metadata
- encrypted artifact files on disk
- OS keyring storage for the long-lived master key
- per-artifact authenticated encryption

Reference ADR:

- [ADR 0001: Local Encrypted Store for Microsoft Graph Artifacts](./ADRs/0001-encrypted-graph-artifact-store.md)

## Current Scope

What exists now:

- a shared storage library in `scripts/lib/storage/`
- a repo-local store directory, configurable through `.env`
- OS-keyring-backed master key creation and reuse
- encrypted artifact write and read helpers for bytes and JSON payloads
- a user-facing initialization script: `scripts/store_init.py`

What is not wired in yet:

- automatic persistence from the existing Graph scripts
- streaming encryption for very large payloads
- key rotation commands
- retention or cleanup commands

## Configuration

Add these values to `.env` if you want to override the defaults:

| Variable | Required | Meaning |
| --- | --- | --- |
| `MSFT_GRAPH_STORE_DIR` | Optional | Root directory for the encrypted local store. Defaults to `.graph_store/` |
| `MSFT_GRAPH_STORE_KEYRING_SERVICE` | Optional | OS keyring service name used to store the wrapped master key |

The store directory is gitignored by default.

## Store Layout

Default layout:

```text
.graph_store/
  index.sqlite3
  index.sqlite3-wal
  index.sqlite3-shm
  artifacts/
    ab/
      abcd1234....bin
```

Important details:

- `index.sqlite3` holds only indexable metadata and wrapped per-artifact keys
- encrypted payload bytes live under `artifacts/`
- the long-lived master key is not stored in the repo; it lives in the OS keyring

## Initialize The Store

Run:

```bash
.venv/bin/python scripts/store_init.py
```

JSON output:

```bash
.venv/bin/python scripts/store_init.py --json
```

What this does:

1. creates the store directory if it does not exist
2. creates the SQLite index and schema
3. creates or reuses the master key in the OS keyring
4. prints the effective paths and keyring slot information

## Security Model

The current implementation is optimized for local desktop usage with minimal user friction.

Protected by default:

- artifact bytes written through the storage helper
- per-artifact data integrity through authenticated encryption
- master key storage through the platform keyring service

Not fully hidden by default:

- index fields needed for lookup and operations such as artifact type, account fingerprint, timestamps, and ciphertext path
- file sizes and artifact counts

Guidance:

- store only non-sensitive searchable metadata in the SQLite index
- place sensitive payload content inside the encrypted artifact body
- continue treating session logs and debug logs as separate data flows; they must not contain decrypted artifact content by default

## Python API

Current shared entry points:

- `GraphArtifactStore.initialize()`
- `GraphArtifactStore.put_bytes(...)`
- `GraphArtifactStore.put_json(...)`
- `GraphArtifactStore.get_bytes(...)`
- `GraphArtifactStore.get_json(...)`
- `GraphArtifactStore.list_artifacts(...)`
- `build_account_fingerprint(...)`

Intended usage pattern for future Graph scripts:

1. build a stable account fingerprint from the signed-in identity
2. fetch the Graph payload
3. store the payload through the shared storage helper
4. log the Graph operation without logging the decrypted artifact body

## Platform Notes

- macOS: the key is stored through Keychain-backed keyring access
- Windows: the key is stored through Credential Locker or another supported keyring backend
- Linux: the keyring backend typically depends on Secret Service support being available

If no supported OS keyring backend is available, `scripts/store_init.py` fails with a clear error instead of silently writing the master key into plaintext repo files.
