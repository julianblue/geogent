import { describe, expect, it } from "vitest";
import type { LangChainMessage } from "@assistant-ui/react-langgraph";

import { deriveThreadTitle } from "./chatApi";

const human = (content: LangChainMessage["content"]): LangChainMessage =>
  ({ type: "human", content }) as LangChainMessage;

describe("deriveThreadTitle", () => {
  it("uses the first human message and collapses whitespace", () => {
    expect(deriveThreadTitle([human("  Show crop\n health  ")])).toBe("Show crop health");
  });

  it("prefers a human turn over a leading system/ai turn", () => {
    const messages = [
      { type: "ai", content: "hi" } as LangChainMessage,
      human("What's the NDVI here?"),
    ];
    expect(deriveThreadTitle(messages)).toBe("What's the NDVI here?");
  });

  it("reads text out of structured content parts", () => {
    expect(deriveThreadTitle([human([{ type: "text", text: "Compare two scenes" }])])).toBe(
      "Compare two scenes",
    );
  });

  it("truncates long titles with an ellipsis", () => {
    const long = "a".repeat(80);
    const title = deriveThreadTitle([human(long)], 20);
    expect(title).toHaveLength(20);
    expect(title?.endsWith("…")).toBe(true);
  });

  it("returns null when there is no usable text", () => {
    expect(deriveThreadTitle([])).toBeNull();
    expect(deriveThreadTitle([human("   ")])).toBeNull();
  });
});
