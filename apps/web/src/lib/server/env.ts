import "server-only";

/** Server-only configuration (read at request time, so one image serves every environment). */
export const serverEnv = {
  /** Auth service on the internal network (Better Auth). */
  authUrl: process.env.AUTH_INTERNAL_URL ?? "http://localhost:3001",
  /** Core API on the internal network. */
  apiUrl: process.env.API_INTERNAL_URL ?? "http://localhost:8000",
};
