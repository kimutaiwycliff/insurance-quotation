/**
 * Better Auth configuration (ADR-0006).
 *
 * Users, sessions, organizations (= tenants), invitations and 2FA live here, in the `auth` schema owned by
 * `auth_owner`. The API trusts only the short-lived JWTs this service signs (JWKS at /api/auth/jwks) and keeps
 * a mirror of memberships, updated by the organization hooks below. Role *keys* live here; what each role may
 * do is owned by the API (ADR-0007).
 */
import { APIError } from "better-auth/api";
import { betterAuth } from "better-auth";
import { bearer, jwt, organization, twoFactor } from "better-auth/plugins";
import { createAccessControl } from "better-auth/plugins/access";
import {
  adminAc,
  defaultStatements,
  memberAc,
  ownerAc,
} from "better-auth/plugins/organization/access";
import { Pool } from "pg";

import { type ApiNotifier, createApiNotifier } from "./api-client.js";
import type { Config } from "./config.js";
import { createMailer, type Mailer } from "./email.js";

/** Agency roles (mirrors app/core/permissions.py Role). Only owner/admin may manage members here. */
export const ROLE_KEYS = ["owner", "admin", "agent", "accounts", "assistant", "viewer"] as const;

const ac = createAccessControl(defaultStatements);
const roles = {
  owner: ac.newRole(ownerAc.statements),
  admin: ac.newRole(adminAc.statements),
  agent: ac.newRole(memberAc.statements),
  accounts: ac.newRole(memberAc.statements),
  assistant: ac.newRole(memberAc.statements),
  viewer: ac.newRole(memberAc.statements),
};

interface OrgClaims {
  org_id: string;
  org_role: string;
  org_name: string;
  org_slug: string | null;
}

/** Active organization claims for the access token, read straight from this service's tables. */
async function orgClaims(
  pool: Pool,
  organizationId: string | null | undefined,
  userId: string,
): Promise<OrgClaims | Record<string, never>> {
  if (!organizationId) return {};
  const { rows } = await pool.query<{ role: string; name: string; slug: string | null }>(
    `SELECT m.role, o.name, o.slug
       FROM member m JOIN organization o ON o.id = m."organizationId"
      WHERE m."organizationId" = $1 AND m."userId" = $2`,
    [organizationId, userId],
  );
  const row = rows[0];
  if (!row) return {}; // stale active org (member removed): no tenant claims
  return { org_id: organizationId, org_role: row.role, org_name: row.name, org_slug: row.slug };
}

interface HookUser {
  id: string;
  email: string;
  name?: string | null;
}
interface HookOrg {
  id: string;
  name: string;
  slug?: string | null;
}

/** 402 from the API means the plan's seats are taken. Unreachable API: allow (never block on an outage). */
async function requireSeat(api: ApiNotifier, orgId: string, userId?: string): Promise<void> {
  const status = await api.ask("/internal/v1/seats/check", { org_id: orgId, user_id: userId ?? null });
  if (status === 402) {
    throw new APIError("FORBIDDEN", {
      message: "All the seats on your plan are taken. Upgrade in Settings → Plan & billing, or remove someone first.",
    });
  }
}

function memberPayload(org: HookOrg, user: HookUser, role: string) {
  return {
    org_id: org.id,
    org_name: org.name,
    org_slug: org.slug ?? null,
    user: { user_id: user.id, email: user.email, name: user.name ?? "" },
    role,
  };
}

export function createAuth(
  config: Config,
  deps: { pool?: Pool; mailer?: Mailer; notifier?: ApiNotifier } = {},
) {
  const pool = deps.pool ?? new Pool({ connectionString: config.databaseUrl, max: 10 });
  const mailer = deps.mailer ?? createMailer(config);
  // Bound after `auth` exists: hooks sign service tokens with this service's own key.
  let signServiceToken: () => Promise<string> = async () => {
    throw new Error("auth not initialised");
  };
  const api = deps.notifier ?? createApiNotifier(config, () => signServiceToken());

  const auth = betterAuth({
    appName: config.appName,
    baseURL: config.baseUrl,
    basePath: "/api/auth",
    secret: config.secret,
    database: pool,
    trustedOrigins: config.trustedOrigins,
    rateLimit: { enabled: config.rateLimitEnabled, storage: "database" },
    advanced: {
      useSecureCookies: config.environment === "production" || config.environment === "staging",
    },
    emailAndPassword: {
      enabled: true,
      requireEmailVerification: true,
      minPasswordLength: 10,
      revokeSessionsOnPasswordReset: true,
      sendResetPassword: async ({ user, url }) => {
        await mailer.send(
          user.email,
          `Reset your ${config.appName} password`,
          `Use this link to choose a new password (valid for one hour):\n\n${url}\n\n` +
            "If you did not ask for this, ignore this email.",
        );
      },
    },
    emailVerification: {
      sendOnSignUp: true,
      autoSignInAfterVerification: true,
      sendVerificationEmail: async ({ user, url }) => {
        await mailer.send(
          user.email,
          `Confirm your email for ${config.appName}`,
          `Welcome! Confirm your email address to start using ${config.appName}:\n\n${url}`,
        );
      },
    },
    socialProviders:
      config.googleClientId && config.googleClientSecret
        ? {
            google: {
              clientId: config.googleClientId,
              clientSecret: config.googleClientSecret,
            },
          }
        : {},
    plugins: [
      organization({
        ac,
        roles,
        creatorRole: "owner",
        invitationExpiresIn: 7 * 24 * 60 * 60,
        sendInvitationEmail: async ({ email, organization: org, inviter, id }) => {
          const url = `${config.trustedOrigins[0] ?? config.baseUrl}/accept-invitation/${id}`;
          await mailer.send(
            email,
            `${inviter.user.name || inviter.user.email} invited you to ${org.name}`,
            `You have been invited to join ${org.name} on ${config.appName}.\n\nAccept: ${url}`,
          );
        },
        organizationHooks: {
          // Plans limit seats (R2.5): refuse before anything is created, with a message the inviter can act on.
          beforeCreateInvitation: async ({ organization: org }) => {
            await requireSeat(api, org.id);
          },
          beforeAcceptInvitation: async ({ organization: org, user }) => {
            await requireSeat(api, org.id, user.id);
          },
          afterCreateOrganization: async ({ organization: org, user }) => {
            await api.post("/internal/v1/tenants", {
              org_id: org.id,
              name: org.name,
              slug: org.slug ?? null,
              owner: { user_id: user.id, email: user.email, name: user.name ?? "" },
            });
          },
          afterAddMember: async ({ organization: org, user, member }) => {
            await api.post("/internal/v1/memberships", memberPayload(org, user, member.role), "PUT");
          },
          afterAcceptInvitation: async ({ organization: org, user, member }) => {
            await api.post("/internal/v1/memberships", memberPayload(org, user, member.role), "PUT");
          },
          afterUpdateMemberRole: async ({ organization: org, user, member }) => {
            await api.post("/internal/v1/memberships", memberPayload(org, user, member.role), "PUT");
          },
          afterRemoveMember: async ({ organization: org, user }) => {
            await api.post("/internal/v1/memberships/remove", { org_id: org.id, user_id: user.id });
          },
        },
      }),
      twoFactor({ issuer: config.appName }),
      jwt({
        jwks: { keyPairConfig: { alg: "EdDSA", crv: "Ed25519" } },
        jwt: {
          issuer: config.jwtIssuer,
          audience: config.jwtAudience,
          expirationTime: "15m",
          definePayload: async ({ user, session }) => ({
            email: user.email,
            name: user.name ?? "",
            mfa_enrolled: Boolean(user.twoFactorEnabled),
            ...(await orgClaims(pool, session.activeOrganizationId, user.id)),
          }),
        },
      }),
      bearer(),
    ],
  });

  signServiceToken = async () => {
    const { token } = await auth.api.signJWT({
      body: {
        // signJWT only sets iat when given; the API requires it (and iss/aud are pinned explicitly).
        payload: {
          sub: "service:auth",
          iat: Math.floor(Date.now() / 1000),
          iss: config.jwtIssuer,
          aud: config.jwtInternalAudience,
        },
        overrideOptions: {
          jwt: {
            issuer: config.jwtIssuer,
            audience: config.jwtInternalAudience,
            expirationTime: "60s",
          },
        },
      },
    });
    return token;
  };

  return { auth, pool };
}

export type Auth = ReturnType<typeof createAuth>["auth"];
