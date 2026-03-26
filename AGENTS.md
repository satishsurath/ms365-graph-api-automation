# AGENTS.md

Repository rules for future script work:

1. Any new or modified script under `scripts/` must have corresponding documentation created or updated.
   The primary script index is `Docs/scripts.md`.
   Update `README.md` too when the user-facing command surface changes.

2. Any read or write operation against Microsoft 365 through Microsoft Graph must emit session logging.
   Route Graph HTTP calls through the shared helper layer so logging stays centralized and consistent.
   Session logs must be redacted by default.
   Verbose payload logging is opt-in via debug mode only.
   Access tokens and refresh tokens must never be written to logs.

3. Session logs must remain local and gitignored.
   Use the configured session log directory rather than writing logs into tracked folders.

4. Prefer shared helper modules for auth, Graph transport, and logging.
   New scripts should inherit the existing conventions rather than reimplementing their own transport or logging behavior.
