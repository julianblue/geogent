"use client";

import { useState } from "react";
import { Archive, MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";
import {
  ThreadListItemPrimitive,
  ThreadListPrimitive,
  useThreadListItem,
  useThreadListItemRuntime,
} from "@assistant-ui/react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";

/**
 * Conversation list (#20). Lists the logged-in user's LangGraph threads via the
 * thread-list adapter and lets them create, switch, rename, archive, and delete
 * conversations. Must render inside an `AssistantRuntimeProvider` wired with a
 * thread-list adapter.
 */
export function ThreadListSidebar() {
  return (
    <ThreadListPrimitive.Root className="flex min-h-0 flex-col gap-2">
      <ThreadListPrimitive.New asChild>
        <Button variant="outline" size="sm" className="w-full justify-start gap-2">
          <Plus className="h-4 w-4" />
          New conversation
        </Button>
      </ThreadListPrimitive.New>
      <div className="min-h-0 flex-1 space-y-0.5 overflow-y-auto">
        <ThreadListPrimitive.Items components={{ ThreadListItem }} />
      </div>
    </ThreadListPrimitive.Root>
  );
}

function ThreadListItem() {
  const itemRuntime = useThreadListItemRuntime();
  const title = useThreadListItem((s) => s.title);
  const [draft, setDraft] = useState<string | null>(null);

  const commitRename = () => {
    const next = draft?.trim();
    if (next) itemRuntime.rename(next);
    setDraft(null);
  };

  if (draft !== null) {
    return (
      <form
        onSubmit={(e) => {
          e.preventDefault();
          commitRename();
        }}
        className="px-1 py-0.5"
      >
        {/* eslint-disable-next-line jsx-a11y/no-autofocus */}
        <Input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commitRename}
          onKeyDown={(e) => {
            if (e.key === "Escape") setDraft(null);
          }}
          aria-label="Rename conversation"
          className="h-8"
        />
      </form>
    );
  }

  return (
    <div className="group flex items-center rounded-md hover:bg-accent data-[active]:bg-accent">
      <ThreadListItemPrimitive.Trigger className="flex-1 truncate px-2 py-1.5 text-left text-sm">
        <ThreadListItemPrimitive.Title fallback="New conversation" />
      </ThreadListItemPrimitive.Trigger>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="mr-1 h-6 w-6 shrink-0 opacity-0 focus-visible:opacity-100 group-hover:opacity-100 data-[state=open]:opacity-100"
            aria-label="Conversation options"
          >
            <MoreHorizontal className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem
            onSelect={(e) => {
              e.preventDefault();
              setDraft(title ?? "");
            }}
          >
            <Pencil className="mr-2 h-4 w-4" />
            Rename
          </DropdownMenuItem>
          <ThreadListItemPrimitive.Archive asChild>
            <DropdownMenuItem onSelect={(e) => e.preventDefault()}>
              <Archive className="mr-2 h-4 w-4" />
              Archive
            </DropdownMenuItem>
          </ThreadListItemPrimitive.Archive>
          <ThreadListItemPrimitive.Delete asChild>
            <DropdownMenuItem
              onSelect={(e) => e.preventDefault()}
              className="text-destructive focus:text-destructive"
            >
              <Trash2 className="mr-2 h-4 w-4" />
              Delete
            </DropdownMenuItem>
          </ThreadListItemPrimitive.Delete>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
