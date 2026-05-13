"use client";

import { useState } from "react";
import { Check, ShieldQuestion, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function ConfirmSaveCard({
  status,
  defaultName,
  wkt,
  onSave,
  onCancel,
}: {
  status: string;
  defaultName: string;
  wkt: string;
  onSave: (name: string) => Promise<void> | void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(defaultName);
  const [submitting, setSubmitting] = useState(false);
  const done = status === "complete";

  async function handleSave() {
    setSubmitting(true);
    try {
      await onSave(name.trim() || defaultName);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card className="my-2 max-w-md border-l-4 border-l-amber-500">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <ShieldQuestion className="h-4 w-4 text-amber-600" />
          Confirm save
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1.5">
          <Label htmlFor="feature-name" className="text-xs">
            Name
          </Label>
          <Input
            id="feature-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={done || submitting}
          />
        </div>
        <div className="text-xs text-muted-foreground">
          Geometry: <span className="font-mono">{wkt.slice(0, 64)}…</span>
        </div>
      </CardContent>
      <CardFooter className="flex justify-end gap-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={onCancel}
          disabled={done || submitting}
        >
          <X className="h-4 w-4" />
          Cancel
        </Button>
        <Button size="sm" onClick={handleSave} disabled={done || submitting}>
          <Check className="h-4 w-4" />
          {done ? "Saved" : submitting ? "Saving…" : "Save"}
        </Button>
      </CardFooter>
    </Card>
  );
}
