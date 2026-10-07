/** RFC 9457 problem+json from the API, mapped to toasts and form field errors. */

export interface FieldProblem {
  field: string;
  message: string;
  code: string;
}

export interface Problem {
  status: number;
  code: string;
  title: string;
  detail?: string;
  request_id?: string;
  errors?: FieldProblem[];
}

export class ApiError extends Error {
  constructor(readonly problem: Problem) {
    super(problem.detail ?? problem.title);
    this.name = "ApiError";
  }

  get status(): number {
    return this.problem.status;
  }

  get code(): string {
    return this.problem.code;
  }
}

export async function parseProblem(response: Response): Promise<Problem> {
  try {
    const body = (await response.json()) as Partial<Problem>;
    if (typeof body.code === "string" && typeof body.title === "string") {
      return { ...body, status: response.status } as Problem;
    }
  } catch {
    // not JSON
  }
  return { status: response.status, code: "http_error", title: response.statusText || "Request failed" };
}

/** "body.legal_name" → "legal_name"; nested paths keep their dots ("address.city"). */
export function fieldName(path: string): string {
  return path.replace(/^(body|query|path)\./, "");
}

/** Field errors keyed by form field name, for react-hook-form's setError. */
export function fieldErrors(problem: Problem): Record<string, string> {
  const out: Record<string, string> = {};
  for (const error of problem.errors ?? []) out[fieldName(error.field)] ??= error.message;
  return out;
}

/** One sentence for a toast: what went wrong and, where we know it, what to do. */
export function problemMessage(problem: Problem): string {
  switch (problem.code) {
    case "version_conflict":
      return "Someone else changed this while you were editing. Reload to see their changes, then try again.";
    case "rate_limited":
      return "Too many requests. Wait a moment and try again.";
    case "permission_denied":
      return "Your role does not allow this. Ask the agency owner or an admin.";
    case "mfa_required":
      return "Turn on two-step sign-in in Security settings to continue.";
    case "unauthenticated":
      return "Your session has ended. Sign in again.";
    case "validation_error":
      return "Some fields need attention.";
    default:
      return problem.detail ?? problem.title;
  }
}
