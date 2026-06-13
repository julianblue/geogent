import { MapWorkspace } from "@/components/workspace/MapWorkspace";
import { requireSession } from "@/lib/auth";

export default async function AppPage() {
  const session = await requireSession();
  return <MapWorkspace userId={String(session.user.id)} />;
}
