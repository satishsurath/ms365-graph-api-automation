# Entra App Setup

This guide walks a user through creating a Microsoft Entra app registration that future scripts in this repo can use to call Microsoft Graph with delegated permissions.

## Recommended Default

For this repo, the recommended starting point is:

- Supported account type: `Accounts in any organizational directory`
- Auth flow: authorization code flow with PKCE
- Redirect URI: `http://localhost`
- Public client flow: enabled
- Scope model: base user scopes plus optional capability bundles

That default best matches the repo's goal of maximum Microsoft 365 automation flexibility.

## When To Use A Different Audience

If you want Outlook.com or other consumer Microsoft accounts to sign in, create a separate app registration with:

- Supported account type: `Accounts in any organizational directory and personal Microsoft accounts`

Use that only if you truly need personal-account sign-in. It trades feature surface for audience breadth:

- Microsoft limits these apps to 30 Graph permissions.
- Not every delegated Graph permission is valid for personal Microsoft accounts.
- Teams, Planner, and many group-backed collaboration scenarios should be treated as work or school only.

## Step 1: Create The App Registration

In the Microsoft Entra admin center:

1. Open `Applications` -> `App registrations`.
2. Select `New registration`.
3. Give the app a clear name such as `ms365-graph-api-automation-local`.
4. Choose the supported account type:
   - Recommended: `Accounts in any organizational directory`
   - Optional alternate: `Accounts in any organizational directory and personal Microsoft accounts`
5. Create the app.

After creation, record these values from the Overview page:

- Application (client) ID
- Directory (tenant) ID

## Step 2: Configure Authentication

Under `Authentication`:

1. Select `Add a platform`.
2. Choose `Mobile and desktop applications`.
3. For a system-browser sign-in flow, add the exact redirect URI:
   - `http://localhost`
4. Under `Advanced settings`, set `Allow public client flows` to `Yes`.
5. Save the configuration.

Notes:

- This repo's planned scripts are local interactive helpers, so a public-client setup is the right fit.
- Do not create a client secret for this delegated localhost desktop-style flow.

## Step 3: Add Microsoft Graph Delegated Permissions

Under `API permissions`:

1. Select `Add a permission`.
2. Choose `Microsoft Graph`.
3. Choose `Delegated permissions`.
4. Add the scopes your scripts need.

Start with the core bundle from [graph-permissions.md](./graph-permissions.md), then add shared-resource and collaboration bundles only if you need them.

Recommended core bundle:

- `User.Read`
- `Mail.ReadWrite`
- `Mail.Send`
- `MailboxSettings.ReadWrite`
- `Calendars.ReadWrite`
- `Contacts.ReadWrite`
- `Files.ReadWrite`
- `Files.ReadWrite.All`
- `Sites.ReadWrite.All`
- `Notes.ReadWrite`
- `Tasks.ReadWrite`
- `People.Read`

Recommended shared-resource extension:

- `Mail.ReadWrite.Shared`
- `Mail.Send.Shared`
- `Calendars.ReadWrite.Shared`
- `Contacts.ReadWrite.Shared`
- `Tasks.ReadWrite.Shared`
- `Notes.ReadWrite.All`

Recommended org-focused collaboration extension:

- `OnlineMeetings.ReadWrite`
- `Presence.ReadWrite`
- `Chat.Create`
- `Chat.ReadWrite`
- `ChatMessage.Send`
- `Channel.ReadBasic.All`
- `ChannelMessage.Send`
- `ChannelMessage.ReadWrite`
- `Team.ReadBasic.All`
- `Group.ReadWrite.All`

## Step 4: Handle Consent Correctly

Delegated scopes fall into three practical buckets:

- User-consentable scopes: often work immediately unless tenant policy blocks user consent.
- Admin-consentable scopes: the user cannot finish setup until an admin grants consent.
- Org-only scopes: even with delegated auth, the API may only make sense for work or school accounts.

Important nuances:

- Microsoft Graph delegated permissions are always constrained by both the granted scope and the signed-in user's own access.
- Even when Microsoft marks a delegated permission as not requiring admin consent by default, a tenant's app-consent policies can still block user consent.
- Teams and Planner scenarios should be treated as organization-focused. Microsoft explicitly says `Group.*` permissions control access to Teams and Planner resources, and personal Microsoft accounts are not supported for those workloads.

## Step 5: Save The App Coordinates In `.env`

Copy `.env.example` to `.env` and fill in the values from the app registration.

For the recommended org-only default:

```dotenv
MSFT_TENANT_ID=organizations
MSFT_CLIENT_ID=your-client-id
MSFT_AUTHORITY=https://login.microsoftonline.com/organizations
MSFT_REDIRECT_URI=http://localhost
```

For a consumer-compatible alternate:

```dotenv
MSFT_TENANT_ID=common
MSFT_CLIENT_ID=your-client-id
MSFT_AUTHORITY=https://login.microsoftonline.com/common
MSFT_REDIRECT_URI=http://localhost
```

## Step 6: Keep OIDC Scopes Separate From Graph Scopes

The Microsoft Graph permissions reference notes that on the Microsoft identity platform v2.0 endpoint:

- `offline_access` is used to explicitly request a refresh token
- `openid` requests an ID token
- `profile` can add identity claims

The same reference also notes that MSAL commonly adds `offline_access`, `openid`, `profile`, and `email` by default. Because of that:

- Keep OIDC scopes separate from the Graph delegated permission list.
- Let your auth library decide whether they must be passed explicitly.
- Do not blindly concatenate OIDC scopes into every Graph scope request.

## Suggested Runtime Validation Strategy For Future Scripts

To fail cleanly, future scripts in this repo should:

1. Declare the minimum required scopes per script or per command.
2. Compare required scopes to configured scope bundles before starting the sign-in flow.
3. If a Graph call fails with `401`, `403`, or `insufficient_scope`, print:
   - the missing scope
   - whether the scope is likely admin-consented
   - whether the workload is work/school only
4. If the user signs in with a personal Microsoft account and calls an org-only API, return a direct message explaining that the API is not available for that account type.

## Setup Checklist

- App registration created
- Supported account type chosen intentionally
- `http://localhost` added as a mobile/desktop redirect URI
- Public client flows enabled
- Delegated Graph permissions added
- Admin consent granted where required
- `.env` populated with client, tenant, authority, redirect URI, and scope bundles

## Troubleshooting

### `AADSTS7000218` during interactive sign-in

If the browser sign-in succeeds but token acquisition fails with:

- `AADSTS7000218`
- `invalid_client`
- `client_assertion` or `client_secret` required

then Microsoft Entra is treating the app as a confidential client during code redemption.

Check these items in the app registration:

- `Authentication` -> `Mobile and desktop applications` contains `http://localhost`
- `Authentication` -> `Advanced settings` -> `Allow public client flows` is `Yes`
- The localhost redirect URI is not only registered under `Web`

This repo's Python scripts use MSAL Python `PublicClientApplication` and assume a public-client localhost flow.

## Source Links

- [Supported account types](https://learn.microsoft.com/en-us/entra/identity-platform/v2-supported-account-types)
- [Desktop app configuration](https://learn.microsoft.com/en-us/entra/identity-platform/scenario-desktop-app-configuration)
- [OAuth 2.0 authorization code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow)
- [Microsoft Graph permissions overview](https://learn.microsoft.com/en-us/graph/permissions-overview)
- [Microsoft Graph permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference)
