import { cookies } from "next/headers";
import { redirect } from "next/navigation";

const COOKIE_NAME = "geogent_session";

export async function GET() {
  cookies().delete(COOKIE_NAME);
  redirect("/login");
}

export async function POST() {
  cookies().delete(COOKIE_NAME);
  redirect("/login");
}
