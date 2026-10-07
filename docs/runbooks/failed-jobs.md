# Runbook: failed background jobs

Jobs run in Procrastinate (schema `jobs`). A failed job stays in `procrastinate_jobs` with status `failed`.

```bash
make jobs-shell                       # Procrastinate shell in the worker container
> list_jobs --status failed           # what failed, with task name and args
> retry <job_id>                      # re-queue one job (tasks are idempotent by rule)
> cancel <job_id>                     # give up on a job that can never succeed
```

Before retrying, read the worker logs for the job id: a bug needs a fix and deploy first. Jobs carry
`tenant_id` in their args, so do not paste args into tickets without redacting personal data.

An HTTP admin endpoint for replay comes with the platform-admin console (no platform-admin identity exists yet).
