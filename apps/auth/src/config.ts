/**
 * Environment configuration. This is the only module that reads process.env.
 * Every variable is documented in the repo's .env.example.
 */

function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} must be set`);
  return value;
}

function optional(name: string, fallback: string): string {
  return process.env[name] || fallback;
}

function list(name: string, fallback: string): string[] {
  return optional(name, fallback)
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

export interface Config {
  environment: string;
  port: number;
  /** Public base URL of this service (cookies, callbacks, links in emails). */
  baseUrl: string;
  secret: string;
  databaseUrl: string;
  trustedOrigins: string[];
  /** JWT claims the API verifies (must match AUTH_ISSUER / AUTH_AUDIENCE in the API). */
  jwtIssuer: string;
  jwtAudience: string;
  jwtInternalAudience: string;
  /** Base URL of the API for organization hooks (internal network). */
  apiInternalUrl: string;
  appName: string;
  emailFrom: string;
  smtpHost: string;
  smtpPort: number;
  smtpSecure: boolean;
  smtpUser: string | undefined;
  smtpPassword: string | undefined;
  googleClientId: string | undefined;
  googleClientSecret: string | undefined;
  rateLimitEnabled: boolean;
}

export function loadConfig(): Config {
  const environment = optional("ENVIRONMENT", "local");
  const secret = required("BETTER_AUTH_SECRET");
  if (secret.length < 32) throw new Error("BETTER_AUTH_SECRET must be at least 32 characters");
  if (environment === "production" && secret.startsWith("dev-only")) {
    throw new Error("Development BETTER_AUTH_SECRET must not be used in production");
  }
  const baseUrl = optional("BETTER_AUTH_URL", "http://localhost:3001");
  return {
    environment,
    port: Number(optional("PORT", "3001")),
    baseUrl,
    secret,
    databaseUrl: required("AUTH_DATABASE_URL"),
    trustedOrigins: list("AUTH_TRUSTED_ORIGINS", "http://localhost:3000"),
    jwtIssuer: optional("AUTH_ISSUER", baseUrl),
    jwtAudience: optional("AUTH_AUDIENCE", "brokeros-api"),
    jwtInternalAudience: optional("AUTH_INTERNAL_AUDIENCE", "brokeros-internal"),
    apiInternalUrl: optional("API_INTERNAL_URL", "http://localhost:8000"),
    appName: optional("APP_NAME", "BrokerOS"),
    emailFrom: optional("EMAIL_FROM", "BrokerOS <no-reply@brokeros.local>"),
    smtpHost: optional("SMTP_HOST", "localhost"),
    smtpPort: Number(optional("SMTP_PORT", "1025")),
    smtpSecure: optional("SMTP_SECURE", "false") === "true",
    smtpUser: process.env.SMTP_USER || undefined,
    smtpPassword: process.env.SMTP_PASSWORD || undefined,
    googleClientId: process.env.GOOGLE_CLIENT_ID || undefined,
    googleClientSecret: process.env.GOOGLE_CLIENT_SECRET || undefined,
    rateLimitEnabled: optional("AUTH_RATE_LIMIT_ENABLED", "true") === "true",
  };
}
