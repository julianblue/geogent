import { CopilotKit } from "@copilotkit/react-core";
import "@copilotkit/react-ui/styles.css";

import { AppHeader } from "@/components/chrome/AppHeader";
import { requireSession } from "@/lib/auth";

export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await requireSession();
  return (
    <CopilotKit
      runtimeUrl="/api/copilotkit"
      agent="geogent"
      properties={{ userId: session.user.id }}
    >
      <div className="flex h-screen min-h-0 flex-col bg-background">
        <AppHeader user={session.user} />
        <div className="relative min-h-0 flex-1">{children}</div>
      </div>
    </CopilotKit>
  );
}
