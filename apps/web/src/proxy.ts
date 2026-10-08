/**
 * UX routing only (never the security boundary, see SPEC_REVIEW §5): signed-out visitors of app pages are sent
 * to sign-in. Every page and the BFF still verify the session server-side.
 */
import { NextResponse, type NextRequest } from "next/server";

const PUBLIC = [/^\/sign-(in|up)/, /^\/two-factor/, /^\/forgot-password/, /^\/reset-password/, /^\/verify-email/, /^\/accept-invitation/, /^\/d\//];
const SESSION_COOKIES = ["better-auth.session_token", "__Secure-better-auth.session_token"];

export function proxy(request: NextRequest): NextResponse {
  const { pathname, search } = request.nextUrl;
  if (PUBLIC.some((re) => re.test(pathname))) return NextResponse.next();
  const signedIn = SESSION_COOKIES.some((name) => request.cookies.has(name));
  if (!signedIn) {
    const url = new URL("/sign-in", request.url);
    if (pathname !== "/") url.searchParams.set("next", `${pathname}${search}`);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  // Skip API routes, the BFF, the anonymous public proxy, Next internals and static files.
  matcher: ["/((?!api/|bff/|public-api/|_next/|favicon.ico|.*\\.[a-z0-9]+$).*)"],
};
