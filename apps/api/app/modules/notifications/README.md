# notifications

In-app notifications (the bell) and per-user preferences (in-app and/or email per kind).

- **Service API:** `notify(session, settings, tenant_id=, user_ids=, kind=, title=, body=, link=)`.
- **Endpoints (own data only):** `GET /notifications`, `GET /notifications/unread-count`,
  `POST /notifications/{id}/read`, `POST /notifications/read-all`, `GET/PUT /notification-preferences`.
- **Kinds:** `link.viewed`, `document.expiring`, `member.joined`.
