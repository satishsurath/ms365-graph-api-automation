# Script Reference

This file documents the Python scripts currently available in this repo.

## Current Script Surface

There are two user-facing scripts:

| Script | Purpose | Primary outcome |
| --- | --- | --- |
| `scripts/auth_login.py` | Run the delegated Microsoft sign-in flow and cache tokens locally | Produces a cached access/refresh token set for later Graph calls |
| `scripts/graph_me.py` | Verify the cached auth flow by calling Microsoft Graph `/me` | Confirms the app registration, scopes, and token cache are working |

There are also three internal helper modules used by those scripts:

| Module | Purpose |
| --- | --- |
| `scripts/lib/config.py` | Loads and validates `.env` settings |
| `scripts/lib/auth.py` | Handles MSAL token acquisition and token-cache persistence |
| `scripts/lib/graph.py` | Performs minimal Microsoft Graph HTTP GET calls |

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

Default output:

- account username
- tenant ID
- authority
- whether the token came from cache or interactive sign-in
- expiry time
- granted scopes

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

Default output:

- display name
- user principal name
- mail
- object ID

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
- surfaces a targeted `AADSTS7000218` fix message for common public-client misconfiguration

### `scripts/lib/graph.py`

Purpose:
Provide a minimal authenticated Graph GET helper for starter scripts.

Notable behaviors:

- uses `urllib` instead of a heavier API client
- returns parsed JSON
- raises a repo-specific `GraphApiError` with HTTP response details

## Files These Scripts Read Or Write

Read:

- `.env`

Write:

- token cache file at `MSFT_TOKEN_CACHE_PATH`

Typically that cache lives under:

- `.tokens/msal_cache.json`

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

## Recommended Documentation Flow For Users

1. Read [Entra app setup](./entra-app-setup.md).
2. Read [Graph delegated permission matrix](./graph-permissions.md).
3. Run `scripts/auth_login.py`.
4. Run `scripts/graph_me.py`.
5. Move on to future workload-specific scripts once auth and `/me` validation are working.
