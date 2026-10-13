# WorkOS auth setup

Goal: the user's email is the `user_id` everywhere, so one person keeps one history across every entryway. Steps 4–7 are not written yet.

| Entryway | How it signs in |
|---|---|
| REST API, AG-UI, A2A | WorkOS token in an `Authorization: Bearer` header |
| MCP (`/mcp`) | WorkOS login in the browser |
| Slack | Nothing to add. Slack already supplies the email |
| Telegram, WhatsApp | Not supported yet (they only supply a platform ID) |

## On the web

1. **WorkOS dashboard, JWT Template:** set `{"email": "{{ user.email }}"}` ([docs](https://workos.com/docs/authkit/jwt-templates)). Keep sign-up off and create a test user with a password.
2. **WorkOS dashboard, Connect → Configuration:** turn on CIMD and add the Resource Indicator `https://<your-public-host>/mcp`. If the dashboard won't save it, ask Claude to add it with the WorkOS MCP (`setAuthkitOauthResources`), then check it with `authkitOauthResources`.
3. **api.slack.com/apps → your app → OAuth & Permissions:** add `users:read` and `users:read.email`, then reinstall the app.

## In the code

4. `.env`: add `WORKOS_CLIENT_ID`, `WORKOS_AUTHKIT_DOMAIN`, and `PUBLIC_URL=https://<your-public-host>`. Use `PUBLIC_URL` for the MCP audience, not `AGENTOS_URL`: `compose.yaml` overrides `AGENTOS_URL` with `http://agentos-api:8000` inside Docker, which would not match the Resource Indicator.
5. `app/settings.py`: add a `WorkOSSettings` class like `SlackSettings`.
6. New file `app/auth.py`: lower-case the token's email (reject tokens without one), verify against `https://api.workos.com/sso/jwks/<client_id>`, and check the issuer `https://api.workos.com`.
7. `app/main.py`: use `AuthKitProvider` for `mcp_auth`. After `app = agent_os.get_app()`, add the auth middleware, skipping `/slack/*` and the MCP OAuth paths.

## Test

8. Get a token (it expires in 5 minutes) and decode it. It must contain `email`.

   ```bash
   curl -s https://api.workos.com/user_management/authenticate \
     -H 'Content-Type: application/json' \
     -d '{"client_id":"<client_id>","client_secret":"<api_key>","grant_type":"password","email":"<you>","password":"<pw>"}'
   ```

9. Run on the host, because compose forces dev mode (auth off):
   `RUNTIME_ENV=prd DB_HOST=localhost JWT_JWKS_FILE=./jwks.json uvicorn app.main:app --port 8001`
10. `curl -F message=hi localhost:8001/agents/learning-coach/runs`: 200 with `-H "Authorization: Bearer $TOKEN"`, 401 without it. AG-UI (`/agui`) and A2A (`/a2a/...`) take the same header.
11. MCP: `claude mcp add --transport http agentos https://<your-public-host>/mcp`, run `/mcp` in Claude Code, and sign in.
12. Send one message from Slack and one over REST. In Postgres, `select user_id, count(*) from <sessions table> group by 1` should show a single email.
