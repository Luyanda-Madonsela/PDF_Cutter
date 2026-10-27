# Google OAuth setup and auth testing

Configure the backend with `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
`GOOGLE_AUTH_REDIRECT_URI`, `GOOGLE_DRIVE_REDIRECT_URI`, and `FRONTEND_URL`.
Register both callback URLs as authorized redirect URIs on the same Google OAuth
web client. For the hosted preview, use:

- `https://papercut-sa.preview.emergentagent.com/api/auth/google/callback`
- `https://papercut-sa.preview.emergentagent.com/api/drive/callback`

The consent screen must include the account used to test sign-in if the OAuth app
is in Testing mode, and the Google Drive API must be enabled to use Drive features.

Sign-in starts at `GET /api/auth/google/login`; the callback verifies Google's
OpenID Connect ID token and establishes a seven-day server-side session cookie.
All app API routes other than `/api/auth/*` require a valid session (cookie or
Bearer token).

GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}
GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET}
GOOGLE_AUTH_REDIRECT_URI=https://papercut-sa.preview.emergentagent.com/api/auth/google/callback
GOOGLE_DRIVE_REDIRECT_URI=https://papercut-sa.preview.emergentagent.com/api/drive/callback
FRONTEND_URL=https://papercut-sa.preview.emergentagent.com
