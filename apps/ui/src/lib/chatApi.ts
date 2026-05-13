import { Client, type ThreadState } from "@langchain/langgraph-sdk";
import type {
  LangChainMessage,
  LangGraphMessagesEvent,
  LangGraphSendMessageConfig,
} from "@assistant-ui/react-langgraph";

const ASSISTANT_ID = process.env.NEXT_PUBLIC_LANGGRAPH_GRAPH_ID ?? "geogent";

function createClient(): Client {
  const apiUrl =
    typeof window === "undefined"
      ? (process.env.LANGGRAPH_URL ?? "http://localhost:2024")
      : new URL("/api/lg", window.location.href).href;
  return new Client({ apiUrl });
}

export async function createThread() {
  return createClient().threads.create();
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
    streamMode: ["messages-tuple", "values", "custom"],
    ...(checkpointId ? { checkpointId } : {}),
  }) as AsyncGenerator<LangGraphMessagesEvent<LangChainMessage>>;
}
