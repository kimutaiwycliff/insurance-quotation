# Tenancy & authentication

```mermaid
sequenceDiagram
    participant B as Browser / app
    participant A as auth (Better Auth)
    participant API as api (FastAPI)
    participant DB as Postgres (auth + app schemas)
    B->>A: sign up, verify email, create organization
    A->>DB: auth.user / organization / member
    A->>API: POST /internal/v1/tenants (service JWT)
    API->>DB: app.tenants + memberships + default numbering (RLS: tenant = uuid5(org_id))
    B->>A: GET /api/auth/token
    A-->>B: access JWT (EdDSA, 15 min, org_id, org_role, mfa_enrolled)
    B->>API: GET /api/v1/... (Bearer JWT)
    API->>A: GET /api/auth/jwks (cached)
    API->>DB: BEGIN; set_config('app.tenant_id'); read membership mirror; ... COMMIT
```

- Tenant isolation: [ADR-0003](../adr/0003-tenancy-and-rls.md). Auth topology: [ADR-0006](../adr/0006-auth-topology.md).
  Roles and permissions: [ADR-0007](../adr/0007-roles-and-permissions.md).
- Request pipeline (`app/platform/deps.py`): verify token → open transaction, set tenant → resolve principal
  (lazy provisioning) → MFA policy → rate limit → permission → endpoint → commit → response.
- `/internal/*` is for service-to-service calls only; the public ingress must not route it, nor `/metrics`.
