"use client";

import {
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
} from "@assistant-ui/react";
import { ArrowDown, SendHorizonal } from "lucide-react";

import { Button } from "@/components/ui/button";

export function Thread() {
  return (
    <ThreadPrimitive.Root className="flex h-full min-h-0 flex-col bg-background">
      <ThreadPrimitive.Viewport className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-3 py-4">
        <ThreadPrimitive.Empty>
          <div className="text-sm italic text-muted-foreground">
            Hi! Ask me to fly to a place, buffer the visible area, or list features in view.
            I&apos;ll always confirm before writing to the database.
          </div>
        </ThreadPrimitive.Empty>
        <ThreadPrimitive.Messages
          components={{ UserMessage, AssistantMessage, SystemMessage: NullMessage }}
        />
        <ScrollToBottomButton />
      </ThreadPrimitive.Viewport>
      <Composer />
    </ThreadPrimitive.Root>
  );
}

function UserMessage() {
  return (
    <MessagePrimitive.Root className="self-end rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground">
      <MessagePrimitive.Parts />
    </MessagePrimitive.Root>
  );
}

function AssistantMessage() {
  return (
    <MessagePrimitive.Root className="self-start max-w-full whitespace-pre-wrap rounded-lg bg-muted px-3 py-2 text-sm text-foreground">
      <MessagePrimitive.Parts />
    </MessagePrimitive.Root>
  );
}

function NullMessage() {
  return null;
}

function Composer() {
  return (
    <ComposerPrimitive.Root className="flex items-end gap-2 border-t border-border p-3">
      <ComposerPrimitive.Input
        placeholder="Ask geogent…"
        rows={1}
        className="min-h-[36px] max-h-32 flex-1 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
      />
      <ComposerPrimitive.Send asChild>
        <Button size="icon" aria-label="Send">
          <SendHorizonal className="h-4 w-4" />
        </Button>
      </ComposerPrimitive.Send>
    </ComposerPrimitive.Root>
  );
}

function ScrollToBottomButton() {
  return (
    <ThreadPrimitive.ScrollToBottom asChild>
      <Button
        size="icon"
        variant="outline"
        className="sticky bottom-2 ml-auto h-7 w-7 rounded-full opacity-90"
        aria-label="Scroll to bottom"
      >
        <ArrowDown className="h-3.5 w-3.5" />
      </Button>
    </ThreadPrimitive.ScrollToBottom>
  );
}
