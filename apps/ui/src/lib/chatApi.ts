import { Client, type ThreadState } from "@langchain/langgraph-sdk";
import type {
  LangChainMessage,
  LangGraphMessagesEvent,
  LangGraphSendMessageConfig,
} from "@assistant-ui/react-langgraph";

const ASSISTANT_ID = process.env.NEXT_PUBLIC_LANGGRAPH_GRAPH_ID ?? "geogent";

export function createClient(): Client {
  const apiUrl =
    typeof window === "undefined"
      ? (process.env.LANGGRAPH_URL ?? "http://localhost:2024")
      : new URL("/api/lg", window.location.href).href;
  return new Client({ apiUrl });
}

export async function createThread() {
  return createClient().threads.create();
}

/**
 * Derive a short, human-readable thread title from the first user turn. Used to
 * label freshly-created conversations in the thread-list sidebar (#20) without
 * waiting on a server-side title model. Returns `null` when there is no usable
 * text (e.g. the first turn is tool-only).
 */
export function deriveThreadTitle(messages: LangChainMessage[], maxLength = 60): string | null {
  const firstHuman = messages.find((m) => m.type === "human");
  const source = firstHuman ?? messages[0];
  if (!source) return null;

  const { content } = source;
  let text = "";
  if (typeof content === "string") {
    text = content;
  } else if (Array.isArray(content)) {
    text = content
      .map((part) => (typeof part === "object" && part && "text" in part ? String(part.text) : ""))
      .join(" ");
  }

  text = text.replace(/\s+/g, " ").trim();
  if (!text) return null;
  return text.length > maxLength ? `${text.slice(0, maxLength - 1).trimEnd()}…` : text;
}

/**
 * Persist a thread title into LangGraph thread metadata. Thread metadata is
 * patched (merged) server-side, so this preserves the `owner` tag set at
 * creation time.
 */
export async function setThreadTitle(threadId: string, title: string): Promise<void> {
  await createClient().threads.update(threadId, { metadata: { title } });
}

export async function getThreadState(
  threadId: string,
): Promise<ThreadState<Record<string, unknown>>> {
  return createClient().threads.getState(threadId);
}

function matchesParentMessages(
  stateMessages: LangChainMessage[] | undefined,
  parentMessages: LangChainMessage[],
): boolean {
  if (!stateMessages || stateMessages.length !== parentMessages.length) return false;
  const haveIds =
    parentMessages.every((m) => typeof m.id === "string") &&
    stateMessages.every((m) => typeof m.id === "string");
  if (!haveIds) return false;
  return parentMessages.every((m, i) => m.id === stateMessages[i]?.id);
}

export async function getCheckpointId(
  threadId: string,
  parentMessages: LangChainMessage[],
): Promise<string | null> {
  const history = await createClient().threads.getHistory(threadId);
  for (const state of history) {
    const stateMessages = (state.values as { messages?: LangChainMessage[] }).messages;
    if (matchesParentMessages(stateMessages, parentMessages)) {
      return state.checkpoint.checkpoint_id ?? null;
    }
  }
  return null;
}

export type SendMessageParams = {
  threadId: string;
  messages: LangChainMessage[];
  config?: LangGraphSendMessageConfig;
  mapState?: unknown;
};

export function sendMessage(
  params: SendMessageParams,
): AsyncGenerator<LangGraphMessagesEvent<LangChainMessage>> {
  const { checkpointId, command, ...restConfig } = params.config ?? {};
  const runConfig = (restConfig.runConfig as Record<string, unknown> | undefined) ?? {};
  const configurable: Record<string, unknown> = {
    ...((runConfig.configurable as Record<string, unknown> | undefined) ?? {}),
  };
  if (params.mapState !== undefined) configurable.map_state = params.mapState;

  return createClient().runs.stream(params.threadId, ASSISTANT_ID, {
    input: command ? undefined : { messages: params.messages },
    command,
    config: { ...runConfig, configurable },
    // "updates" is required — @assistant-ui/react-langgraph only routes
    // `__interrupt__` into useLangGraphInterruptState from Updates events.
    // Drop it and our Sentinel2RenderTool (and any other interrupt handler)
    // never fires.
    streamMode: ["messages-tuple", "values", "updates", "custom"],
    ...(checkpointId ? { checkpointId } : {}),
  }) as AsyncGenerator<LangGraphMessagesEvent<LangChainMessage>>;
}
