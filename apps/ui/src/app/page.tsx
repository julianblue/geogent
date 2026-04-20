import { MapView } from "@/components/map/MapView";
import { CopilotSidebar } from "@/components/copilot/CopilotSidebar";

export default function HomePage() {
  return (
    <main className="relative h-screen w-screen">
      <MapView />
      <CopilotSidebar />
    </main>
  );
}
