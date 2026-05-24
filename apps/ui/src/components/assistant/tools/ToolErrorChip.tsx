"use client";

import { AlertCircle } from "lucide-react";

function messageFrom(error: unknown): string {
  if (!error) return "Tool failed.";
  if (typeof error === "string") return error;
  if (error instanceof Error) return error.message;
  return JSON.stringify(error);
}

export function ToolErrorChip({ label, error }: { label: string; error: unknown }) {
  return (
    <div className="my-2 flex max-w-md items-start gap-2 rounded-md border border-destructive bg-destructive/10 px-3 py-2 text-sm text-destructive dark:bg-destructive/5 dark:text-red-200">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="min-w-0">
        <div className="font-medium">{label} failed</div>
        <div className="break-words text-xs opacity-90">{messageFrom(error)}</div>
      </div>
    </div>
  );
}
