# Mission Control Security Stance

This document defines the security posture for Mission Control across authentication, transport, input handling, and operational concerns. It supplements the auth model in the product plan, the credential storage model in the Comms Bridge spec, and the RLS tenant isolation in the persistence strategy.

## Principles

1. **Defense in depth.** No single layer is trusted to be the only barrier. Application-layer org scoping, database-layer RLS, and network-layer TLS each independently prevent unauthorized access.
2. **Least privilege by default.** Contributors cannot perform Admin actions. Sub-agents cannot access resources outside their assigned task. API keys grant access to exactly one org.
3. **Fail closed.** Missing or invalid credentials result in rejection, not degraded access. Ambiguous org membership returns 404, not 403.
4. **Secrets never at rest in plaintext in application code or logs.** Keys are hashed in the database, masked in logs, and loaded from environment or secrets managers at runtime.
5. **Self-hosted parity.** Self-hosted deployments get the same security model as the hosted offering. There is no "lite" security mode.

---

## Transport Security

### TLS

All communication between clients (Web UI, agents, Comms Bridge) and the Mission Control server must use TLS 1.2 or higher.

**Hosted deployment:** Caddy handles TLS termination with automatic certificate provisioning via Let's Encrypt. TLS 1.2 is the minimum; TLS 1.3 is preferred and negotiated when the client supports it.

**Self-hosted deployment:** The bundled Caddy configuration provides automatic TLS if the instance has a public domain. For internal/private deployments without a public domain, the self-hosting guide documents how to configure Caddy with a custom certificate or use a reverse proxy that handles TLS termination.

**Internal services:** Communication between the FastAPI server, PostgreSQL, and Redis within a single docker-compose stack uses the Docker internal network (not exposed to the host). If these services are on separate hosts (e.g., RDS for PostgreSQL), TLS is required on those connections:

```python
# database.py
DATABASE_URL = "postgresql+asyncpg://user:pass@rds-host:5432/mc?ssl=require"
```

### HSTS

The server sends `Strict-Transport-Security` headers on all responses:

```
Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
```

This instructs browsers to always use HTTPS, even if the user types `http://`. The `max-age` is two years.

---

## CORS Policy

### Hosted Deployment

CORS is restricted to the exact origin of the hosted Web UI:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://mc.openclaw.dev"],
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
    allow_credentials=True,      # required for HttpOnly cookie auth
    max_age=3600,
)
```

No wildcard origins. No `Access-Control-Allow-Origin: *`. The `allow_credentials=True` flag is required because the Web UI authenticates via HttpOnly cookies, and CORS credentialed requests demand an explicit origin.

### Self-Hosted Deployment

The allowed origin is configured via environment variable:

```bash
MC_CORS_ORIGIN="https://mc.mycompany.internal"
```

If not set, CORS is disabled entirely (no cross-origin requests allowed). The server never falls back to a wildcard origin.

### Agent API Requests

Agents call the API from server-side code (Comms Bridge, scripts), not from browsers. CORS does not apply to these requests. Agent requests authenticate via `Authorization: Bearer` header, not cookies.

---

## CSRF Protection

CSRF is a concern only for browser-based requests that use cookie authentication (the Web UI). Agent requests use header-based API keys and are not vulnerable to CSRF.

### Strategy: Double-Submit Cookie

The server issues a CSRF token as a separate cookie (`mc_csrf`, **not** HttpOnly — JavaScript must be able to read it) alongside the session JWT cookie (`mc_session`, HttpOnly). The Web UI reads the CSRF token cookie and includes it as a request header on every state-changing request:

```
X-CSRF-Token: {value from mc_csrf cookie}
```

The server validates that the header value matches the cookie value. Since a cross-origin attacker can cause the browser to send cookies but cannot read them (due to SameSite and CORS restrictions), the attacker cannot produce the matching header.

### Implementation

```python
# middleware.py

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

async def csrf_middleware(request: Request, call_next):
    # Skip CSRF for API key auth (agents) and safe methods
    if request.headers.get("Authorization") or request.method in SAFE_METHODS:
        return await call_next(request)

    # Validate CSRF token for cookie-authenticated requests
    cookie_token = request.cookies.get("mc_csrf")
    header_token = request.headers.get("X-CSRF-Token")

    if not cookie_token or not header_token or cookie_token != header_token:
        return JSONResponse(
            status_code=403,
            content={"error": {"code": "CSRF_VALIDATION_FAILED", "message": "Invalid or missing CSRF token.", "status": 403}}
        )

    return await call_next(request)
```

### Cookie Attributes

| Cookie | HttpOnly | Secure | SameSite | Path | Max-Age |
|--------|----------|--------|----------|------|---------|
| `mc_session` (JWT) | Yes | Yes | Lax | `/` | 1 hour |
| `mc_csrf` | No | Yes | Lax | `/` | 1 hour |

`SameSite=Lax` prevents the browser from sending cookies on cross-origin POST requests (the primary CSRF vector) while allowing normal navigation links to work.

`Secure=Yes` ensures cookies are only sent over HTTPS.

---

## Authentication Details

### Session JWT (Web UI)

The session JWT issued after OIDC login contains:

```json
{
  "sub": "usr_abc123",
  "org_ids": ["org_xyz789", "org_def456"],
  "active_org": "org_xyz789",
  "role": "contributor",
  "iat": 1739500000,
  "exp": 1739503600
}
```

**Signing:** JWTs are signed with HS256 using a server-side secret (`MC_JWT_SECRET` environment variable). The secret is at least 256 bits and generated randomly on first deployment. RS256 (asymmetric) is available as a configuration option for deployments that need to verify tokens in other services.

**Expiry:** 1 hour. The Web UI calls `POST /auth/refresh` before expiry to extend the session. Refresh extends the session by issuing a new JWT; it does not use a separate refresh token. If the session has expired, the user is redirected to the OIDC login flow.

**Revocation:** JWTs are stateless and cannot be individually revoked before expiry. For immediate revocation (e.g., user removed from org, security incident), the server maintains a short-lived revocation list in Redis. On every request, the middleware checks the JWT's `jti` (JWT ID) against the revocation list. Entries expire from the list after the JWT's `max-age` (1 hour), keeping the list small.

**Org switching:** When a user switches orgs in the UI, the server issues a new JWT with the updated `active_org` claim. The previous JWT is added to the revocation list.

### API Key Authentication (Agents)

**Hashing:** API keys are generated as random 256-bit values, prefixed for identification (`mc_ak_live_` for persistent agents, `mc_ak_tmp_` for sub-agents). The full key is returned to the Admin exactly once on creation. The server stores only the bcrypt hash (cost factor 12) in the `api_key_hash` column of `users_orgs` (persistent agents) or `sub_agents` (temporary).

**Validation:** On every request, the server extracts the key from the `Authorization: Bearer` header, bcrypt-compares it against stored hashes. To avoid scanning all hashes, the key prefix includes an encoded hint of the user ID:

```
mc_ak_live_{userId_short}_{random}
```

The server extracts `userId_short`, looks up the specific hash, and compares. This makes validation O(1) instead of O(n).

**Rotation:**

```
POST /api/v1/orgs/{orgSlug}/users/{userId}/api-keys/rotate
```

1. Server generates a new key.
2. Server hashes and stores the new key.
3. Server returns the new key to the Admin (shown once).
4. The old key remains valid for a grace period (configurable, default: 24 hours) to allow the operator to update the Comms Bridge secrets file without downtime.
5. After the grace period, the old hash is deleted. Requests with the old key return 401.

The grace period is tracked in a `api_key_previous_hash` column with an `api_key_previous_expires_at` timestamp. The middleware checks both hashes during the grace window.

**Revocation:**

```
DELETE /api/v1/orgs/{orgSlug}/users/{userId}/api-keys
```

Immediate. The hash is deleted. Any in-flight request with the old key that arrives after deletion returns 401. The Comms Bridge detects this via its SSE connection (which also returns 401) and stops the affected agent.

### SSE Connection Authentication

SSE uses the same authentication as REST endpoints. The initial `GET /api/v1/orgs/{orgSlug}/events/stream` request must include valid credentials:

- **Web UI:** HttpOnly session cookie (sent automatically by the browser).
- **Agents (via Comms Bridge):** `Authorization: Bearer {apiKey}` header.

The SSE connection is authenticated once at establishment. The server maintains an in-memory record of the authenticated user for each open SSE connection. If the user's credentials are revoked (JWT revoked, API key deleted), the server closes the SSE connection by sending a `session.revoked` event followed by connection termination. The Comms Bridge handles this by attempting reauthentication (which will fail, triggering the error flow documented in the Bridge spec).

**Token refresh during long-lived SSE connections:** For Web UI SSE connections, the 1-hour JWT expiry is shorter than a typical SSE session. The server does not require re-authentication on an established SSE connection — the initial authentication is sufficient. However, if the SSE connection drops and the client reconnects, the reconnection request must carry a valid (refreshed) JWT.

### WebSocket Authentication

WebSocket connections authenticate during the HTTP upgrade handshake. The `WS /api/v1/orgs/{orgSlug}/channels/ws` request is validated as follows:

- **Web UI:** Session cookie is included in the upgrade request (browsers send cookies on WebSocket handshake). The server validates the JWT before accepting the upgrade.
- **Agents:** If an agent needs a direct WebSocket connection (not typical — the Comms Bridge uses REST for outbound messages), it passes the API key as a query parameter: `ws://...?token={apiKey}`. Query parameter auth is acceptable here because WebSocket does not support custom headers during handshake.

**Post-handshake security:** Once the WebSocket connection is established, the server maintains the authenticated identity in memory. Messages sent over the WebSocket are attributed to this identity. If the user's credentials are revoked, the server sends a close frame with code `4001` (custom: authentication revoked) and terminates the connection.

**WebSocket query parameter key exposure:** The `?token=` parameter will appear in server access logs. The server's access log configuration must exclude query parameters from WebSocket upgrade requests, or mask the token value. This is configured in the Caddy reverse proxy:

```
# Caddyfile
log {
    output file /var/log/caddy/access.log
    format filter {
        wrap console
        fields {
            request>uri query_delete token
        }
    }
}
```

---

## Input Validation

### Strategy

All input validation is performed at two layers:

1. **Pydantic models (API boundary).** Every request body and query parameter is validated by a Pydantic model before reaching business logic. Invalid input returns 400 with a structured error response. This catches type errors, missing fields, and format violations.

2. **Database constraints (storage boundary).** Foreign key constraints, CHECK constraints, unique constraints, and NOT NULL constraints enforce data integrity even if application-level validation is bypassed (e.g., a bug in business logic, a direct database migration).

### Specific Validation Rules

**String fields:**

- All string inputs are stripped of leading/trailing whitespace.
- Maximum lengths are enforced at the Pydantic level:

| Field | Max Length |
|-------|-----------|
| Org name | 100 |
| Org slug | 50 |
| Project name | 200 |
| Task title | 500 |
| Channel message content | 10,000 |
| Sub-agent instructions | 50,000 |
| Comment (on transitions) | 2,000 |
| Display name | 100 |
| URL (links, evidence) | 2,048 |

- Org slugs are validated against a pattern: lowercase alphanumeric and hyphens only (`^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$`). A reserved slug list prevents collisions with API routes (e.g., `api`, `auth`, `admin`, `health`).

**Enum fields:** Lifecycle stages, task statuses, priorities, roles, and user types are validated against explicit allowed values. The shared package defines these as Python enums, and Pydantic rejects any value not in the enum.

**UUID fields:** All resource IDs are validated as UUID format. Non-UUID IDs return 400, not 404.

**URL fields:** Links and evidence URLs are validated for format (must be absolute URLs with `https://` scheme). No `javascript:`, `data:`, or relative URLs.

**JSON/JSONB fields:** The `settings` and `payload` fields accept arbitrary JSON but are validated for maximum depth (10 levels) and maximum size (64 KB) to prevent abuse.

**Message content:** Channel messages are treated as plain text. No HTML rendering. OpenClaw commands (`/status`, etc.) are identified by a leading `/` but are otherwise treated as text. This prevents XSS by design — the frontend renders message content as text nodes, never as inner HTML.

### SQL Injection Prevention

SQLAlchemy's parameterized queries are the sole interface to the database. Raw SQL strings are never interpolated with user input. The only raw SQL in the codebase is the RLS `SET` statement, which uses parameterized binding:

```python
await session.execute(
    text("SET app.current_org_id = :org_id"),
    {"org_id": str(org_id)}  # parameterized, not f-string
)
```

Alembic migrations may contain raw DDL (e.g., trigger creation), but these are developer-authored and not influenced by user input.

---

## Rate Limiting

Rate limiting is deferred to v2 (see API design doc), but the security-critical foundation is established in v1:

**Connection limits:** The server enforces a maximum number of concurrent SSE and WebSocket connections per org:

| Connection Type | Default Limit (per org) |
|----------------|------------------------|
| SSE | 100 |
| WebSocket | 200 |

Exceeding the limit returns `429 Too Many Requests` with a `Retry-After` header. These limits prevent a single org (or a compromised API key) from exhausting server resources.

**Request size limits:** The ASGI server (Uvicorn) enforces a maximum request body size of 1 MB. Requests exceeding this are rejected before reaching the application. The data export download endpoint is the only exception (responses can be larger, but request bodies are still limited).

**Authentication attempt limits:** Failed login attempts (OIDC callback errors, invalid API keys) are logged with the source IP. In the hosted deployment, Caddy's rate limiting module limits authentication endpoints to 10 requests per minute per IP. Self-hosted deployments can configure this threshold.

---

## Dependency Security

### Python Dependencies

- **Pinned versions:** All dependencies are pinned via `uv.lock` to exact versions. No floating version ranges in production.
- **Vulnerability scanning:** `uv audit` runs in CI on every push, checking dependencies against the OSV database. Build fails if a known vulnerability with a severity of HIGH or CRITICAL is found in a direct dependency.
- **Update cadence:** Dependencies are reviewed and updated monthly. Security patches are applied immediately.

### Frontend Dependencies

- **Pinned versions:** `package-lock.json` pins all dependencies.
- **Vulnerability scanning:** `npm audit` runs in CI. Same severity thresholds as Python.

### Docker Base Images

- **Minimal base:** `python:3.12-slim` for both server and Bridge images. No full OS image.
- **Image scanning:** Container images are scanned with Trivy in the release workflow before being pushed to GHCR.
- **Non-root execution:** Both Dockerfiles use a non-root user:

```dockerfile
RUN useradd --create-home appuser
USER appuser
```

---

## Secrets Management

### Where Secrets Live

| Secret | Storage | Accessed By |
|--------|---------|-------------|
| `MC_JWT_SECRET` | Environment variable (server) | Server: JWT signing/verification |
| `MC_DATABASE_URL` | Environment variable (server) | Server: PostgreSQL connection |
| `MC_REDIS_URL` | Environment variable (server) | Server: Redis connection |
| OIDC client secrets | Environment variables (server) | Server: OIDC provider authentication |
| Agent API keys (hashed) | PostgreSQL `api_key_hash` column | Server: API key validation |
| Agent API keys (plaintext) | Operator's secrets file or secrets manager | Comms Bridge: runtime authentication |
| Ephemeral sub-agent keys (hashed) | PostgreSQL `api_key_hash` column | Server: sub-agent validation |

### Secrets Never Appear In

- Application source code or configuration files committed to version control.
- Log output (keys are masked to prefix + `...`).
- Error responses to clients.
- The OpenAPI spec.
- Docker image layers (secrets are injected at runtime via environment, not baked into images).
- Browser-accessible state (JWT contents are not sensitive — they contain user ID and role, not keys).

### Rotation

| Secret | Rotation Method | Downtime |
|--------|----------------|----------|
| `MC_JWT_SECRET` | Update env var, restart server. All existing JWTs are invalidated (users must re-login, max 1 hour disruption). | Brief (restart duration) |
| `MC_DATABASE_URL` | Update env var, restart server. | Brief |
| Agent API keys | Rotate via API (24-hour grace period). Update secrets file on Bridge host. No restart needed during grace period. | Zero (grace period) |
| OIDC client secrets | Rotate in provider (GitHub/Google), update env var, restart server. | Brief |

---

## Security Headers

The server includes the following headers on all responses:

```python
# middleware.py

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "0",                          # disabled; CSP is the modern replacement
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' wss://*.openclaw.dev; frame-ancestors 'none';",
}
```

**CSP notes:**

- `connect-src 'self' wss://*.openclaw.dev` allows WebSocket connections to the same origin and the hosted domain.
- `'unsafe-inline'` for styles is required by Tailwind's utility classes. If Tailwind is configured to output external CSS files only, this can be tightened to `'self'`.
- `frame-ancestors 'none'` prevents the application from being embedded in iframes (clickjacking protection), equivalent to `X-Frame-Options: DENY`.

Self-hosted deployments must update the CSP `connect-src` directive to include their own WebSocket domain.

---

## Audit and Logging

### Security-Relevant Events

The following events are logged with full context (actor, org, IP, timestamp) and persisted to the event log:

| Event | Trigger |
|-------|---------|
| `auth.login_success` | Successful OIDC login |
| `auth.login_failure` | Failed OIDC callback (invalid code, provider error) |
| `auth.api_key_failure` | Request with invalid or revoked API key |
| `auth.session_revoked` | JWT added to revocation list |
| `user.created` | New user added to org |
| `user.removed` | User removed from org |
| `user.role_changed` | User role updated |
| `api_key.rotated` | Agent API key rotated |
| `api_key.revoked` | Agent API key revoked |
| `sub_agent.created` | Sub-agent spawned with ephemeral credentials |
| `sub_agent.terminated` | Sub-agent terminated, ephemeral key revoked |
| `org.settings_changed` | Org-level settings modified |
| `org.deletion_initiated` | Org deletion grace period started |
| `export.requested` | Data export initiated |

These events are immutable (enforced by the database trigger documented in the persistence strategy) and are included in data exports.

### Log Output

Application logs (stdout, captured by Docker) use structured JSON format via structlog:

```json
{
  "timestamp": "2026-02-13T10:15:00Z",
  "level": "warning",
  "event": "api_key_validation_failed",
  "org_slug": "acme-robotics",
  "source_ip": "203.0.113.42",
  "key_prefix": "mc_ak_live_usr_a...",
  "reason": "key_revoked"
}
```

Sensitive fields are never included in log output. The `key_prefix` field shows only the identifying prefix, never the full key.

---

## Incident Response Considerations

### Compromised API Key

1. Admin revokes the key immediately via `DELETE /api/v1/orgs/{orgSlug}/users/{userId}/api-keys`.
2. Server closes the agent's SSE connection and rejects all subsequent requests.
3. Admin reviews the event log filtered by the compromised agent's user ID to assess what actions were taken.
4. Admin provisions a new key and updates the Bridge secrets file.

### Compromised Admin Account

1. Remove the admin from the org via another admin, or if sole admin, use the platform-level admin (hosted) or direct database access (self-hosted) to revoke access.
2. Rotate `MC_JWT_SECRET` to invalidate all sessions.
3. Rotate all agent API keys provisioned by the compromised admin.
4. Review the event log for `org.settings_changed`, `user.created`, and `api_key.rotated` events during the compromised period.

### Data Breach Suspicion

1. Suspend the org (read-only mode) to prevent further data exfiltration.
2. Rotate all secrets (JWT secret, database credentials, API keys).
3. Export and review the event log for the affected time period.
4. Notify affected users per applicable breach notification requirements.
