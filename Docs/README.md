# Docs

This folder documents how users should register and configure a Microsoft Entra app so local helper scripts can call Microsoft Graph on their behalf.

## The Key Choice

There are two different optimization targets, and they are not the same:

| Goal | Best supported account type | Why |
| --- | --- | --- |
| Maximum Microsoft 365 automation coverage | `Accounts in any organizational directory` | Best fit for Teams, Planner, group-backed workloads, and broader enterprise collaboration scenarios. Microsoft allows up to 400 requested permissions for organizational audiences. |
| Widest sign-in audience | `Accounts in any organizational directory and personal Microsoft accounts` | Lets consumer accounts sign in, but Microsoft limits these apps to 30 Graph permissions and not every delegated scope works for personal accounts. |

For this repo, the default recommendation is the first option: `Accounts in any organizational directory`.

## What To Read

- [Entra app setup](./entra-app-setup.md)
- [Graph delegated permission matrix](./graph-permissions.md)
- [Script reference](./scripts.md)
- [Encrypted artifact store](./storage.md)
- [Architecture decision records](./ADRs/README.md)

## Working Assumption For This Repo

- Auth model: delegated auth
- Flow: OAuth 2.0 authorization code flow with PKCE
- Redirect URI: `http://localhost`
- Token refresh: `offline_access`
- App type: public client / desktop-style local tooling

## Why This Repo Recommends An Org-Focused Default

The repo is intended to automate as much of an MS365 account as practical. That pushes the design toward work or school tenants because:

- Teams, Planner, group-backed resources, and several collaboration APIs are organization-centric.
- Microsoft Graph marks some delegated permissions as valid for personal Microsoft accounts, but not all.
- Apps that support both organizational and personal Microsoft accounts are capped at 30 Graph permissions, which tightens how much surface area one app registration can cover.

## Source Links

- [Supported account types](https://learn.microsoft.com/en-us/entra/identity-platform/v2-supported-account-types)
- [Desktop app configuration](https://learn.microsoft.com/en-us/entra/identity-platform/scenario-desktop-app-configuration)
- [OAuth 2.0 authorization code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow)
- [Microsoft Graph permissions overview](https://learn.microsoft.com/en-us/graph/permissions-overview)
- [Microsoft Graph permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference)
