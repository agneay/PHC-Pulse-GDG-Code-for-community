# Security Policy

PHC Pulse is a hackathon prototype built on **synthetic data**. No patient-level or real facility
data is stored. Please still report anything that could matter if it were deployed for real.

## Supported versions

Only the latest commit on `main` is maintained. There are no versioned releases yet.

## Reporting a vulnerability

Please report privately through GitHub:
**Security → Advisories → Report a vulnerability** on
<https://github.com/agneay/PHC-Pulse-GDG-Code-for-community/security/advisories/new>.

Do not open a public issue for security problems. Include the endpoint or file, the steps to
reproduce, and what an attacker could do. We aim to acknowledge reports within 3 days and to share
a fix or a decision within 14 days.

## Known limitations (by design in the demo)

These are deliberate for the prototype and are **not** in scope as vulnerabilities, but must change
before any real deployment:

- **Open demo sign-in.** `/api/auth/login` issues any persona (national, state, district, PHC) so
  judges can switch roles. A real deployment needs real identities (e.g. Google Identity / ABHA).
- **Anonymous read access** returns the national view for GET requests. All writes require a signed
  token that expires after `PHC_TOKEN_TTL_SECONDS` (12 hours by default).
- **Feature-phone webhooks** (`/api/ussd`, `/api/sms`, `/api/dialogflow/webhook`) identify the
  worker by caller ID only; a real gateway must add a shared secret or signature check.
- **Single-instance SQLite** store that is re-seeded when the demo date changes.

## Hardening already in place

- HMAC-signed, expiring tokens; the server refuses to start on Cloud Run with the demo secret.
- Row-level scoping on every read and write; only the donor side can release stock in a transfer.
- Static files are served only from the built frontend folder (path traversal is blocked).
- No cross-origin browser access unless `PHC_CORS_ORIGINS` is set.
- Gemini API keys are stored in Secret Manager by `scripts/deploy.sh`, never in the image.
