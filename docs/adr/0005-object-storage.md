# ADR-0005: Object storage — S3 API, RustFS for development and CI

- Status: Accepted (2026-10-07)
- Supersedes: MinIO (`docs/PROJECT_SPEC.md` §4.3, §10.1)

## Context
The MinIO community repository was archived in February 2026, and its Docker images were removed, so there will be
no further fixes. We need an S3-compatible store for local development and CI that supports presigned PUT/GET,
bucket CORS and versioning.

## Decision
- The application uses **only the S3 API** (aioboto3/boto3, `endpoint_url`, path-style addressing), so production can use AWS S3 or Cloudflare R2.
- Dev and CI use **RustFS 1.0.1** (`rustfs/rustfs`, Apache‑2.0). Garage is the fallback if RustFS proves unsuitable (no versioning there).
- Buckets are provisioned by `python -m scripts.storage_init` (idempotent: bucket, versioning, public-access block where supported, CORS). It replaces MinIO's `mc`.
- The S3 client is opened once per process and reused (client creation blocks the event loop).

## Consequences
- RustFS reached GA only in September 2026, so it is used for dev/CI, not production.
- M2 adds presigned URLs. It will need a public endpoint setting (`S3_PUBLIC_ENDPOINT_URL`) so browsers can reach dev storage.
