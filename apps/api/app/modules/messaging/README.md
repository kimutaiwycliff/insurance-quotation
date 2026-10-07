# messaging

Outbound email with a log, templates per event, streams and suppression (ADR-0024).

- **Service API:** `queue_email(session, tenant_id=, event=, to=, context=, ...)` inside the business transaction;
  the job `messaging.send_email` sends it.
- **Endpoints:** `GET /messages`, `POST /messages/test-email`, `GET /message-templates`,
  `PUT/DELETE /message-templates/{event}/{locale}`; public `GET/POST /public/unsubscribe/{token}`.
- **Events:** `document.shared`, `document.expiring` (reminders), `notification.email`, `test.email`.
- **Permissions:** `message:read`, `message_template:manage`.
