# tenancy

Tenants (agencies), the membership mirror of Better Auth organization members, and branches.

- **Entities:** `Tenant` (RLS key `id` = `uuid5(org_id)`; organization settings), `Membership` (user within a
  tenant: role, status, profile), `Branch` (archived, never deleted).
- **Endpoints:** `GET /me`; `GET/PATCH /organization` (If-Match); `GET /members`; `GET /roles`;
  `GET/POST /branches`, `GET/PATCH /branches/{id}` (If-Match; `archived: true` archives).
- **Internal:** `POST /internal/v1/tenants`, `PUT /internal/v1/memberships`, `POST /internal/v1/memberships/remove`.
  These are called by the auth service's organization hooks; all are idempotent.
- **Permissions:** `org:read`, `org:update`, `member:read`, `branch:read`, `branch:manage`.
- **Audit actions:** `organization.updated`, `branch.created`, `branch.updated`.
- **Provisioning:** creates the tenant and seeds default numbering schemes (`numbering.service`), through the hook
  or lazily on the first request.
