import type { Metadata } from "next";
import "./globals.css";
import "@copilotkit/react-ui/styles.css";
import { CopilotKit } from "@copilotkit/react-core";

export const metadata: Metadata = {
  title: "geogent",
  description: "Agentic geospatial analytics and insights",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="h-full">
        <CopilotKit runtimeUrl="/api/copilotkit" agent="geogent">
          {children}
        </CopilotKit>
      </body>
    </html>
  );
}
