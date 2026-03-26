# ms365-graph-api-automation

Starter repo for helper scripts that trigger Microsoft 365 user actions through the Microsoft Graph API.

The repo is being structured around delegated authentication for an interactive user, using the authorization code flow with a localhost redirect URI and refresh-token support.

## Recommended App Model

If the goal is maximum automation coverage, use a Microsoft Entra app registration with this supported account type:

- `Accounts in any organizational directory`

That choice is narrower than allowing personal Microsoft accounts, but it is the better default for this repo because:

- It aligns better with Microsoft 365 workloads such as Teams, Planner, group-backed resources, presence, and organization-level collaboration APIs.
- Microsoft allows up to 400 requested permissions for organizational audiences, while apps that also support personal Microsoft accounts are limited to 30 Graph permissions.
- Several delegated Microsoft Graph permissions are valid only for work or school accounts, even when sign-in itself supports personal accounts.

If you later want consumer-account support for Outlook.com and similar scenarios, the cleaner approach is usually a second app registration with:

- `Accounts in any organizational directory and personal Microsoft accounts`

That audience is broader for sign-in, but it is not the same thing as broader feature support.

## Docs

- [Docs overview](Docs/README.md)
- [Entra app setup](Docs/entra-app-setup.md)
- [Graph delegated permission matrix](Docs/graph-permissions.md)

## Quick Start

1. Read [Docs/entra-app-setup.md](Docs/entra-app-setup.md).
2. Copy `.env.example` to `.env`.
3. Fill in your Entra app values and scope bundles.
4. Build scripts against the permission bundles documented in [Docs/graph-permissions.md](Docs/graph-permissions.md).

## Python Helper Scripts

Install the starter dependencies:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Run an interactive login using the core scope bundle from `.env`:

```bash
.venv/bin/python scripts/auth_login.py
```

If you want to consent the broader shared-resource and collaboration bundles too:

```bash
.venv/bin/python scripts/auth_login.py --include-shared --include-collab
```

Smoke test the cached token against Microsoft Graph `/me`:

```bash
.venv/bin/python scripts/graph_me.py
```

## Starter Config

The repo now includes:

- `Docs/` for setup and permission guidance
- `.env.example` for app coordinates and scope bundles
- `.tokens/` ignored in git for local token cache files
- `scripts/` for the initial Python auth and verification helpers
