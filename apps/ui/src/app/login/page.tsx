import { Globe2 } from "lucide-react";

import { LoginForm } from "@/app/login/LoginForm";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function LoginPage() {
  return (
    <main className="relative flex min-h-screen items-center justify-center bg-muted/40 px-4 py-12">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,_hsl(var(--primary)/0.06),_transparent_60%)]"
      />
      <Card className="relative w-full max-w-sm">
        <CardHeader className="space-y-3 text-center">
          <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Globe2 className="h-5 w-5" />
          </div>
          <CardTitle className="text-xl">Sign in to geogent</CardTitle>
          <CardDescription>
            Agentic geospatial analytics. Use your seeded credentials to continue.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <LoginForm />
        </CardContent>
      </Card>
    </main>
  );
}
