"use client";

import { useState } from "react";
import { Check, Pencil, ShieldQuestion, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { WidgetDefinition, WidgetRenderProps } from "@/components/assistant/widgets/types";

export type ApprovalField = { name: string; label: string; value: string };

export type ApprovalWidgetData = {
  status: string;
  /** What the agent wants to do, e.g. "Save feature". */
  title: string;
  /** Optional context line (geometry preview, target, …). */
  description?: string;
  /** Editable fields surfaced under "Edit"; omit for a plain approve/deny. */
  fields?: ApprovalField[];
  approveLabel?: string;
  onApprove: (values: Record<string, string>) => Promise<void> | void;
  onDeny: () => void;
};

/**
 * Generalized human-in-the-loop approval (#19): "The agent wants to X —
 * Approve / Edit / Deny", driven by a LangGraph interrupt. Any mutating tool
 * can reuse this instead of a bespoke card; ConfirmFeatureSaveTool is the first
 * consumer. Inline-only — approvals are acted on in the transcript.
 */
function ApprovalInline({ data }: WidgetRenderProps<ApprovalWidgetData>) {
  const { status, title, description, fields, approveLabel, onApprove, onDeny } = data;
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries((fields ?? []).map((f) => [f.name, f.value])),
  );
  const [editing, setEditing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const done = status === "complete";
  const hasFields = (fields ?? []).length > 0;

  async function handleApprove() {
    setSubmitting(true);
    try {
      await onApprove(values);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card className="my-2 max-w-md border-l-4 border-l-amber-500">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <ShieldQuestion className="h-4 w-4 text-amber-600" />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {fields?.map((field) => (
          <div key={field.name} className="space-y-1.5">
            <Label htmlFor={`approval-${field.name}`} className="text-xs">
              {field.label}
            </Label>
            <Input
              id={`approval-${field.name}`}
              value={values[field.name] ?? ""}
              onChange={(e) => setValues((v) => ({ ...v, [field.name]: e.target.value }))}
              disabled={done || submitting || !editing}
            />
          </div>
        ))}
        {description ? (
          <div className="text-xs text-muted-foreground">{description}</div>
        ) : null}
      </CardContent>
      <CardFooter className="flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={onDeny} disabled={done || submitting}>
          <X className="h-4 w-4" />
          Deny
        </Button>
        {hasFields ? (
          <Button
            variant="outline"
            size="sm"
            onClick={() => setEditing((e) => !e)}
            disabled={done || submitting}
          >
            <Pencil className="h-4 w-4" />
            {editing ? "Done" : "Edit"}
          </Button>
        ) : null}
        <Button size="sm" onClick={handleApprove} disabled={done || submitting}>
          <Check className="h-4 w-4" />
          {done ? "Done" : submitting ? "Working…" : (approveLabel ?? "Approve")}
        </Button>
      </CardFooter>
    </Card>
  );
}

export const approvalWidget: WidgetDefinition<ApprovalWidgetData> = {
  type: "approval",
  Inline: ApprovalInline,
};
