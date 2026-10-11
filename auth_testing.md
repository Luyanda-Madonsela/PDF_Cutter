# Auth testing (Emergent Google Auth)
1. Create test user + session in mongo (db test_database): users {user_id,email,name,picture,created_at}; user_sessions {user_id, session_token, expires_at (+7d), created_at}
2. curl $API/api/auth/me -H "Authorization: Bearer <token>"
3. Browser: add cookie session_token (domain=app host, path=/, httpOnly, secure, sameSite=None), then goto app.
All /api/* routes (except /api/auth/*) require a session (cookie or Bearer).
