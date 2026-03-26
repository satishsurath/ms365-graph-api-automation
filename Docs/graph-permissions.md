# Graph Delegated Permission Matrix

This file groups delegated Microsoft Graph scopes by capability area so repo scripts can request only what they need while still giving advanced users a path to broader automation coverage.

## How To Read This File

- `Core` scopes are the recommended starting point for most user-content automation.
- `Shared` scopes extend access into delegated shared resources.
- `Collaboration` scopes are more org-focused and are best treated as work or school features.
- `OIDC` scopes are identity scopes, not Microsoft Graph delegated permissions.

## OIDC Scopes

Keep these separate from Graph scopes:

| Scope | Purpose | Notes |
| --- | --- | --- |
| `openid` | Request an ID token | OIDC scope, not a Graph permission |
| `profile` | Add profile claims to the ID token | OIDC scope, not a Graph permission |
| `offline_access` | Request a refresh token | OIDC scope, not a Graph permission |

The Microsoft Graph permissions reference also notes that MSAL commonly adds `openid`, `profile`, `offline_access`, and `email` automatically. Future scripts should not assume they always need to pass these explicitly.

## Core User-Content Scopes

| Capability | Delegated scope | Delegated admin consent required | Personal Microsoft account support | Notes |
| --- | --- | --- | --- | --- |
| Sign-in and basic profile | `User.Read` | No | Yes | Good baseline for almost every interactive script |
| Mail read/write | `Mail.ReadWrite` | No | Yes | Full mailbox item CRUD for the signed-in user |
| Mail send | `Mail.Send` | No | Yes | Can send mail without also granting full mailbox write access |
| Mailbox settings | `MailboxSettings.ReadWrite` | No | Yes | Time zone, automatic replies, working hours, and related settings |
| Calendar read/write | `Calendars.ReadWrite` | No | Yes | Full access to the signed-in user's calendars |
| Contacts read/write | `Contacts.ReadWrite` | No | Yes | Full access to the signed-in user's contacts |
| User drive files | `Files.ReadWrite` | No | Yes | Full access to the signed-in user's files; Microsoft notes this also covers shared files for personal accounts |
| Files the user can access | `Files.ReadWrite.All` | No | Yes | Broader delegated file access across content the user can access |
| SharePoint and list items | `Sites.ReadWrite.All` | No | Yes | Useful for SharePoint libraries and list-backed automation |
| OneNote notebooks | `Notes.ReadWrite` | No | Yes | Full access to the signed-in user's OneNote notebooks |
| To Do / tasks | `Tasks.ReadWrite` | No | Yes | User tasks and task lists |
| Relevant people graph | `People.Read` | No | Yes | Useful for contact suggestions and recent-communication logic |

## Shared-Resource Extensions

These scopes are useful when scripts need delegated access to shared mailboxes, delegate calendars, shared contacts, shared tasks, or notebooks the user can access.

| Capability | Delegated scope | Delegated admin consent required | Personal Microsoft account support | Notes |
| --- | --- | --- | --- | --- |
| Shared mail read/write | `Mail.ReadWrite.Shared` | No | Work/school only | Microsoft explicitly marks this scope as valid only for work or school accounts |
| Send on behalf of others | `Mail.Send.Shared` | No | Work/school only | Needed for delegated send-on-behalf scenarios |
| Shared calendars | `Calendars.ReadWrite.Shared` | No | Treat as org-focused | Covers delegate and shared calendars |
| Shared contacts | `Contacts.ReadWrite.Shared` | No | Treat as org-focused | Covers contacts the user has access to, including shared contacts |
| Shared tasks | `Tasks.ReadWrite.Shared` | No | Treat as org-focused | Includes shared tasks the user can access |
| Notebooks user can access | `Notes.ReadWrite.All` | No | Not marked as personal-account available | Broadens OneNote access to notebooks the user can access in the organization |

## Collaboration And Meeting Extensions

These scopes are most useful in work or school tenants. Some are user-consentable, but the workloads themselves are still organization-centric.

| Capability | Delegated scope | Delegated admin consent required | Personal Microsoft account support | Notes |
| --- | --- | --- | --- | --- |
| Online meetings | `OnlineMeetings.ReadWrite` | No | Treat as org-focused | Create and read online meetings on behalf of the user |
| Presence automation | `Presence.ReadWrite` | No | Treat as org-focused | Read and update the signed-in user's presence |
| Create chats | `Chat.Create` | No | Treat as org-focused | Create new chats |
| Read and write chat threads | `Chat.ReadWrite` | No | Treat as org-focused | One-to-one and group chat thread access |
| Send chat messages | `ChatMessage.Send` | No | Treat as org-focused | Least-privileged send-only chat permission |
| Read channel names | `Channel.ReadBasic.All` | No | Treat as org-focused | Useful for channel discovery without full message access |
| Send channel messages | `ChannelMessage.Send` | No | Treat as org-focused | Least-privileged send-only channel permission |
| Read and write channel messages | `ChannelMessage.ReadWrite` | Yes | Treat as org-focused | Higher-risk Teams message access |
| Read team names and descriptions | `Team.ReadBasic.All` | No | Treat as org-focused | Basic team discovery |
| Read and write groups | `Group.ReadWrite.All` | Yes | No | Microsoft explicitly ties `Group.*` permissions to Teams and Planner and says personal Microsoft accounts are not supported |

## Practical Scope Bundles

### Minimal interactive bundle

Use this when a script only needs basic user content:

```text
User.Read
Mail.ReadWrite
Mail.Send
MailboxSettings.ReadWrite
Calendars.ReadWrite
Contacts.ReadWrite
Files.ReadWrite
Notes.ReadWrite
Tasks.ReadWrite
People.Read
```

### Broad content bundle

Add this when scripts need shared content, SharePoint, or wider file access:

```text
Files.ReadWrite.All
Sites.ReadWrite.All
Mail.ReadWrite.Shared
Mail.Send.Shared
Calendars.ReadWrite.Shared
Contacts.ReadWrite.Shared
Tasks.ReadWrite.Shared
Notes.ReadWrite.All
```

### Org collaboration bundle

Add this only when the scripts truly need collaboration workloads:

```text
OnlineMeetings.ReadWrite
Presence.ReadWrite
Chat.Create
Chat.ReadWrite
ChatMessage.Send
Channel.ReadBasic.All
ChannelMessage.Send
ChannelMessage.ReadWrite
Team.ReadBasic.All
Group.ReadWrite.All
```

## Guidance For Future Scripts

Each future script should declare a small required-scope set instead of using every configured scope all the time. A practical pattern is:

1. Keep broad bundles in `.env`.
2. Let each script map features to the minimum required scopes.
3. Request only the scopes needed for the current action.
4. If the configured app registration or current tenant cannot grant a scope, fail with a direct message that names the missing scope and whether admin consent or a work/school account is likely required.

## Source Links

- [Microsoft Graph permissions overview](https://learn.microsoft.com/en-us/graph/permissions-overview)
- [Microsoft Graph permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference)
- [Desktop app configuration](https://learn.microsoft.com/en-us/entra/identity-platform/scenario-desktop-app-configuration)
