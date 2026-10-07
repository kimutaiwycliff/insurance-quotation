# Runbook: rotate auth signing keys and secrets

## JWKS signing key (Ed25519, Better Auth `jwks` table)
Access and service tokens are signed with the newest key in `auth.jwks`. The API caches the JWKS for
`AUTH_JWKS_CACHE_SECONDS` and refetches on an unknown `kid` (at most every `AUTH_JWKS_MIN_REFETCH_SECONDS`).

Planned rotation:
1. Create the new key. Either let Better Auth create it (configure `jwks.rotationInterval`), or delete nothing
   and insert a new key through a one-off script calling the jwt plugin's key creation.
2. New tokens carry the new `kid`. The API picks the new key up on first sight; old tokens (≤ 15 min) still
   verify because the old public key stays in the JWKS.
3. After 15 minutes plus the cache TTL, remove the old key (or let `gracePeriod` expire it).

Emergency (key compromise):
1. Delete the compromised row from `auth.jwks` (as `auth_owner`), so a new key is created on the next signing.
2. Restart the API pods to drop their JWKS cache immediately. Tokens signed with the old key now fail with
   `401 unauthenticated`, so users sign in again (sessions themselves are unaffected).
3. Revoke sessions if the attacker may hold them: `DELETE FROM auth.session` (everyone signs in again).

## BETTER_AUTH_SECRET
Encrypts the private JWKS keys and signs cookies. Rotating it invalidates sessions and makes stored private keys
unreadable: delete `auth.jwks` rows in the same change, deploy the new secret, and expect everyone to sign in
again. Store it only in the secrets manager.

## Service-to-service tokens
Hook tokens use the same JWKS (`aud=AUTH_INTERNAL_AUDIENCE`, `sub=service:auth`, 60 s), so there is no separate
secret to rotate. If `/internal/*` is ever exposed by mistake, close the ingress first: tokens are short-lived
but valid.
