# tasks

Follow-ups and to-dos, optionally linked to a record (`entity_type`, `entity_id`; clients are checked for
visibility).

- **Endpoints:** `GET /tasks` (`due`: overdue, today, upcoming, none, all, using the agency's timezone),
  `GET /tasks/counts`, `POST /tasks`, `PATCH /tasks/{id}` (edit, reassign, `done`).
- **Reminders:** `tasks.enqueue_due_reminders` (every 5 min) scans through `app.tasks_due_for_reminder()`
  (SECURITY DEFINER), then `tasks.remind` notifies the assignee once (`task.due`).
- **Scoping:** members see tasks assigned to or created by them; `task:read:all` sees all.
