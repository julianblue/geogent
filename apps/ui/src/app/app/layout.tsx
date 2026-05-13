import { AppHeader } from "@/components/chrome/AppHeader";
import { requireSession } from "@/lib/auth";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const session = await requireSession();
  return (
    <div className="flex h-screen min-h-0 flex-col bg-background">
      <AppHeader user={session.user} />
      <div className="relative min-h-0 flex-1">{children}</div>
    </div>
  );
}
