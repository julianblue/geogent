import { NextRequest, NextResponse } from "next/server";

const COOKIE_NAME = "geogent_session";

export function middleware(req: NextRequest) {
  const token = req.cookies.get(COOKIE_NAME)?.value;
  const { pathname } = req.nextUrl;

  if (pathname === "/login" && token) {
    return NextResponse.redirect(new URL("/app", req.url));
  }
  if (pathname.startsWith("/app") && !token) {
    return NextResponse.redirect(new URL("/login", req.url));
  }
  // Defense-in-depth: the proxy + langgraph routes only forward whatever
  // cookie is present, but reject unauthenticated callers at the edge so we
  // don't leak agent capabilities or proxy errors to anonymous traffic.
  if ((pathname.startsWith("/api/proxy") || pathname.startsWith("/api/lg")) && !token) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/", "/app/:path*", "/login", "/api/proxy/:path*", "/api/lg/:path*"],
};
