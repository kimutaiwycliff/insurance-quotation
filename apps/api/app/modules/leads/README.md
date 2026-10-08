# leads

Sales pipeline: `new → contacted → quoted → won | lost`.

- **Endpoints:** `GET/POST /leads`, `GET /leads/pipeline` (counts and estimated premium per stage, follow-ups
  due), `GET/PATCH /leads/{id}`, `POST /leads/{id}/convert` (creates or links a client; idempotent).
- **Rules:** `won` only through conversion; `lost` needs a reason; agents assign leads only to themselves;
  assigning someone else notifies them (`lead.assigned`).
- **Scoping:** `lead:read:all` / `lead:read:own`.
