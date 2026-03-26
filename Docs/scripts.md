# Script Reference

This file documents the Python scripts currently available in this repo.

## Current Script Surface

There are four user-facing scripts:

| Script | Purpose | Primary outcome |
| --- | --- | --- |
| `scripts/auth_login.py` | Run the delegated Microsoft sign-in flow and cache tokens locally | Produces a cached access/refresh token set for later Graph calls |
| `scripts/graph_me.py` | Verify the cached auth flow by calling Microsoft Graph `/me` | Confirms the app registration, scopes, and token cache are working |
| `scripts/mail_send.py` | Send an email as the signed-in Microsoft 365 user | Triggers a real delegated Graph action using the minimal `Mail.Send` scope |
| `scripts/store_init.py` | Initialize the local encrypted Graph artifact store | Creates the SQLite index, artifact directory, and OS-keyring-backed master key |

There are also five internal helper modules used by those scripts:

| Module | Purpose |
| --- | --- |
| `scripts/lib/config.py` | Loads and validates `.env` settings |
| `scripts/lib/auth.py` | Handles MSAL token acquisition and token-cache persistence |
| `scripts/lib/graph.py` | Performs shared Microsoft Graph HTTP operations |
| `scripts/lib/session_logging.py` | Writes per-session JSONL logs for script, auth, and Graph activity |
| `scripts/lib/storage/` | Provides the local encrypted artifact store used by future Graph-caching scripts |

## Shared Prerequisites

Before running any script:

1. Create and populate `.env`.
2. Install dependencies:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

3. Make sure your app registration is configured for:
   - delegated permissions
   - `http://localhost`
   - public client flows enabled

Supporting docs:

- [Entra app setup](./entra-app-setup.md)
- [Graph delegated permission matrix](./graph-permissions.md)

## Configuration The Scripts Expect

The scripts load these environment variables from `.env`:

| Variable | Required | Meaning |
| --- | --- | --- |
| `MSFT_TENANT_ID` | Yes | Tenant selector such as `organizations`, `common`, or a specific tenant ID/domain |
| `MSFT_CLIENT_ID` | Yes | Entra application client ID |
| `MSFT_AUTHORITY` | Recommended | Microsoft identity authority URL; defaults from tenant if omitted |
| `MSFT_REDIRECT_URI` | Yes | Must be a localhost HTTP redirect such as `http://localhost` |
| `MSFT_OIDC_SCOPES` | Optional | OIDC helper scopes such as `openid profile offline_access`; currently retained for future scripts and config clarity rather than being passed explicitly by these starter commands |
| `MSFT_GRAPH_SCOPES` | Yes | Base delegated Graph scopes |
| `MSFT_GRAPH_SCOPES_SHARED` | Optional | Shared-resource delegated scope bundle |
| `MSFT_GRAPH_SCOPES_COLLAB` | Optional | Collaboration and org-focused delegated scope bundle |
| `MSFT_TOKEN_CACHE_PATH` | Yes | Local MSAL token cache path, typically under `.tokens/` |
| `MSFT_SESSION_LOG_DIR` | Optional | Directory for per-session JSONL logs; defaults to `.session_logs/` |
| `MSFT_SESSION_LOG_DEBUG` | Optional | When `true`, include verbose request/response and identity details in session logs; defaults to `false` |
| `MSFT_GRAPH_STORE_DIR` | Optional | Root directory for the encrypted local Graph artifact store; defaults to `.graph_store/` |
| `MSFT_GRAPH_STORE_KEYRING_SERVICE` | Optional | OS keyring service name used for the graph store master key |

## Session Logging

Every real Microsoft Graph read or write operation now produces session logs under `MSFT_SESSION_LOG_DIR`.

Current logging behavior:

- one JSONL log file per script session
- `session_started` and `session_finished` events
- auth events such as cache lookup, interactive sign-in start, and token acquisition
- Graph request, response, and error events for shared HTTP operations
- safe-by-default logging: method, redacted path, status, elapsed time, scope data, payload shape summaries, and summarized errors
- no access tokens or refresh tokens are written to the session logs
- verbose request/response, detailed error bodies, and identity details are available only when `MSFT_SESSION_LOG_DEBUG=true`

Default log location:

- `.session_logs/`

Git behavior:

- the session log directory is gitignored
- logs stay local to the machine running the scripts

## Encrypted Artifact Store

This repo now includes a starter encrypted local store for Graph artifacts.

Current behavior:

- SQLite index for operational metadata
- encrypted artifact files in `MSFT_GRAPH_STORE_DIR`
- OS keyring storage for the long-lived master key
- per-artifact authenticated encryption through the shared storage helper

Supporting docs:

- [Encrypted artifact store](./storage.md)
- [ADR 0001: Local Encrypted Store for Microsoft Graph Artifacts](./ADRs/0001-encrypted-graph-artifact-store.md)

## `scripts/auth_login.py`

Purpose:
Run interactive sign-in, request the selected Graph delegated scopes, and persist tokens to the configured cache file.

Typical usage:

```bash
.venv/bin/python scripts/auth_login.py
```

Common variants:

```bash
.venv/bin/python scripts/auth_login.py --include-shared
.venv/bin/python scripts/auth_login.py --include-collab
.venv/bin/python scripts/auth_login.py --include-shared --include-collab
.venv/bin/python scripts/auth_login.py --scope Files.Read
.venv/bin/python scripts/auth_login.py --login-hint user@contoso.com
.venv/bin/python scripts/auth_login.py --force-interactive
```

What it does:

1. Loads and validates `.env`.
2. Builds the requested Graph scope set from the configured bundles plus any `--scope` overrides.
3. Tries to acquire a token silently from the local cache.
4. If no valid token is found, launches the browser for Microsoft sign-in and consent.
5. Saves the updated MSAL cache to `MSFT_TOKEN_CACHE_PATH`.
6. Writes a per-session JSONL log file under `MSFT_SESSION_LOG_DIR`.

Default output:

- account username
- tenant ID
- authority
- whether the token came from cache or interactive sign-in
- expiry time
- granted scopes
- session log file path

Useful flags:

| Flag | Meaning |
| --- | --- |
| `--env-file PATH` | Load a non-default `.env` file |
| `--include-shared` | Add `MSFT_GRAPH_SCOPES_SHARED` to the token request |
| `--include-collab` | Add `MSFT_GRAPH_SCOPES_COLLAB` to the token request |
| `--scope VALUE` | Append an extra delegated Graph scope |
| `--login-hint VALUE` | Prefill the sign-in experience with a user hint |
| `--force-interactive` | Skip cache lookup and force a fresh sign-in |
| `--json` | Return a structured JSON summary |
| `--print-access-token` | Print only the access token |

When to use it:

- first-time sign-in
- granting new scopes
- refreshing consent after changing the app registration
- confirming the cache path and granted scopes

## `scripts/graph_me.py`

Purpose:
Call Microsoft Graph `/me` with the configured delegated scopes and cached token flow.

Typical usage:

```bash
.venv/bin/python scripts/graph_me.py
```

Common variants:

```bash
.venv/bin/python scripts/graph_me.py --json
.venv/bin/python scripts/graph_me.py --force-interactive
.venv/bin/python scripts/graph_me.py --login-hint user@contoso.com
```

What it does:

1. Loads and validates `.env`.
2. Builds the requested Graph scope set.
3. Reuses the same token-acquisition path as `auth_login.py`.
4. Calls `GET https://graph.microsoft.com/v1.0/me?$select=id,displayName,userPrincipalName,mail`.
5. Prints a compact profile summary or raw JSON.
6. Writes request and response details to the current session log.

Default output:

- display name
- user principal name
- mail
- object ID
- session log file path

Useful flags:

| Flag | Meaning |
| --- | --- |
| `--env-file PATH` | Load a non-default `.env` file |
| `--include-shared` | Add `MSFT_GRAPH_SCOPES_SHARED` to the token request |
| `--include-collab` | Add `MSFT_GRAPH_SCOPES_COLLAB` to the token request |
| `--scope VALUE` | Append an extra delegated Graph scope |
| `--login-hint VALUE` | Prefill the sign-in experience with a user hint |
| `--force-interactive` | Skip cache lookup and force a fresh sign-in |
| `--json` | Print the full Graph JSON response |

When to use it:

- validating a new Entra app registration
- verifying the localhost delegated flow works
- confirming the cache contains a usable token
- checking whether the current user can reach Graph successfully

## `scripts/mail_send.py`

Purpose:
Send an email as the signed-in Microsoft 365 user through `POST /me/sendMail`.

Typical usage:

```bash
.venv/bin/python scripts/mail_send.py \
  --to someone@example.com \
  --subject "Hello from Graph" \
  --body "This message was sent by the repo helper script."
```

Safe validation example:

```bash
.venv/bin/python scripts/mail_send.py \
  --to someone@example.com \
  --subject "Dry run" \
  --body "This will not be sent." \
  --dry-run
```

Common variants:

```bash
.venv/bin/python scripts/mail_send.py --to someone@example.com --subject "HTML test" --body-file body.html --body-type html
.venv/bin/python scripts/mail_send.py --to someone@example.com --cc team@example.com --subject "Status" --body "Done"
.venv/bin/python scripts/mail_send.py --to someone@example.com --subject "No Sent Items copy" --body "Test" --no-save-to-sent-items
```

What it does:

1. Builds a Graph `sendMail` payload from the CLI arguments.
2. Requests only the minimal delegated scope required for this action: `Mail.Send`.
3. Uses the shared auth flow and cached token path.
4. Calls `POST https://graph.microsoft.com/v1.0/me/sendMail`.
5. Treats HTTP `202 Accepted` as success.
6. Writes the outgoing Graph action and response metadata to the current session log.

Required inputs:

- at least one `--to` recipient
- `--subject`
- either `--body` or `--body-file`

Useful flags:

| Flag | Meaning |
| --- | --- |
| `--to VALUE` | One or more recipients; repeat the flag or use comma-separated values |
| `--cc VALUE` | Optional CC recipients |
| `--bcc VALUE` | Optional BCC recipients |
| `--subject VALUE` | Required subject line |
| `--body VALUE` | Inline message body |
| `--body-file PATH` | Read the message body from a file |
| `--body-type text|html` | Choose plain text or HTML body format |
| `--login-hint VALUE` | Optional UPN/email hint for sign-in |
| `--force-interactive` | Skip cache lookup and force sign-in |
| `--dry-run` | Print the constructed request summary without sending mail |
| `--json` | Print structured JSON output |
| `--no-save-to-sent-items` | Do not keep a copy in Sent Items |

When to use it:

- verifying a real write/action path works against Graph
- sending notifications, reminders, or simple automation emails
- validating that the repo can perform a delegated side-effect, not just read profile data

## `scripts/store_init.py`

Purpose:
Initialize the local encrypted Graph artifact store and confirm the OS-keyring-backed master key is available.

Typical usage:

```bash
.venv/bin/python scripts/store_init.py
```

JSON output:

```bash
.venv/bin/python scripts/store_init.py --json
```

What it does:

1. Loads and validates `.env`.
2. Resolves the graph store directory and keyring service name.
3. Creates the SQLite index and artifact directory if they do not exist.
4. Creates or reuses the store master key in the OS keyring.
5. Prints the effective store paths, schema version, artifact count, and keyring slot information.

Default output:

- store directory
- SQLite index path
- artifact directory path
- schema version
- artifact count
- keyring service
- keyring account slot
- master key status

Useful flags:

| Flag | Meaning |
| --- | --- |
| `--env-file PATH` | Load a non-default `.env` file |
| `--json` | Print a structured JSON summary |

When to use it:

- bootstrapping the encrypted local artifact store
- validating that the OS keyring backend is available
- confirming where future Graph artifact payloads will be stored

## Internal Helper Modules

These are not the primary user entrypoints, but they define the current script architecture.

### `scripts/lib/config.py`

Purpose:
Load `.env`, validate the minimum required values, normalize authorities and cache paths, and build scope bundles.

Notable behaviors:

- rejects non-localhost redirect URIs
- rejects localhost redirect URIs with non-root paths
- resolves relative cache paths relative to the repo root
- deduplicates scopes while preserving order

### `scripts/lib/auth.py`

Purpose:
Wrap MSAL Python public-client auth and persistent token caching.

Notable behaviors:

- uses `PublicClientApplication`
- attempts silent cache reuse before browser sign-in
- persists a serializable MSAL cache on disk
- returns a normalized token result with granted scopes and token source
- avoids logging tokens in both normal and debug modes
- surfaces a targeted `AADSTS7000218` fix message for common public-client misconfiguration

### `scripts/lib/graph.py`

Purpose:
Provide a minimal authenticated Graph GET helper for starter scripts.

Notable behaviors:

- uses `urllib` instead of a heavier API client
- returns parsed JSON for GET and JSON-capable POST calls
- raises a repo-specific `GraphApiError` with HTTP response details
- emits request, response, and error events into the active session log
- logs redacted metadata by default and only logs full payloads in debug mode

### `scripts/lib/session_logging.py`

Purpose:
Create one structured JSONL session log per script run and keep auth and Graph activity correlated within that session.

Notable behaviors:

- creates one log file per script session
- stores timestamped JSONL events
- records session metadata, auth events, Graph reads, Graph writes, and failures
- supports a safe default mode and an opt-in verbose debug mode
- keeps logs local in a gitignored directory

### `scripts/lib/storage/`

Purpose:
Provide a shared encrypted local store for future Graph artifact caching and retrieval.

Notable behaviors:

- uses SQLite for indexable metadata
- stores ciphertext payloads as separate files under the graph store directory
- keeps the long-lived master key in the OS keyring instead of a repo file
- encrypts each artifact independently with authenticated encryption
- exposes helper methods for byte payloads, JSON payloads, reads, and listing

## Files These Scripts Read Or Write

Read:

- `.env`

Write:

- token cache file at `MSFT_TOKEN_CACHE_PATH`
- session log files under `MSFT_SESSION_LOG_DIR`
- graph store files under `MSFT_GRAPH_STORE_DIR`
- graph store master key entry in the OS keyring service named by `MSFT_GRAPH_STORE_KEYRING_SERVICE`

Typically that cache lives under:

- `.tokens/msal_cache.json`

Typical session log location:

- `.session_logs/20260326T000000Z-graph_me.py-<session-id>.jsonl`

Typical graph store location:

- `.graph_store/index.sqlite3`
- `.graph_store/artifacts/<prefix>/<artifact-id>.bin`

## Troubleshooting

### Browser sign-in opens, then token acquisition fails with `AADSTS7000218`

Cause:
The app registration is still being treated as a confidential client.

Fix:

- ensure `http://localhost` is registered under `Mobile and desktop applications`
- ensure `Allow public client flows` is enabled
- do not depend on a `Web` redirect URI for this local public-client flow

See [Entra app setup](./entra-app-setup.md).

### The script says a required environment variable is missing

Cause:
`.env` is incomplete or the script is pointed at the wrong file.

Fix:

- compare your `.env` with `.env.example`
- use `--env-file` if you keep multiple environment files

### The script opens a browser even though you already signed in before

Possible causes:

- requested scopes changed
- token cache file was deleted
- cached refresh token is expired or invalid
- `--force-interactive` was used

### Graph returns `403` or `insufficient privileges`

Cause:
The current token lacks a required delegated scope, or tenant policy/admin consent is blocking use of that scope.

Fix:

- add the correct delegated permission to the app registration
- grant admin consent if required
- rerun `scripts/auth_login.py` to refresh consent
- compare the requested capability against [graph-permissions.md](./graph-permissions.md)

### You want to inspect what happened during a Graph script run

Open the latest JSONL file in `MSFT_SESSION_LOG_DIR`.

Those logs contain:

- session metadata
- auth flow events
- each Graph request
- each Graph response or error
- completion status for the script session

### You want to validate `scripts/mail_send.py` without sending a real email

Use `--dry-run`.

That path:

- validates the CLI input
- builds the outgoing Graph payload
- prints a request summary
- skips authentication and skips the actual `sendMail` call

### `scripts/store_init.py` says no OS keyring backend is available

Cause:
The current machine does not have a supported keyring backend available to Python.

Fix:

- on macOS, confirm the script can access Keychain normally
- on Windows, confirm the environment can use a Credential Locker-backed keyring
- on Linux, install or configure a Secret Service compatible backend
- rerun `scripts/store_init.py` after the backend is available

## Recommended Documentation Flow For Users

1. Read [Entra app setup](./entra-app-setup.md).
2. Read [Graph delegated permission matrix](./graph-permissions.md).
3. Run `scripts/auth_login.py`.
4. Run `scripts/graph_me.py`.
5. Use `scripts/mail_send.py --dry-run`.
6. Use `scripts/mail_send.py` for the first real delegated action.
7. Move on to future workload-specific scripts once auth, `/me`, and mail send are working.
