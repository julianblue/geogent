# ADR 0001: Library choice for agent-driven UI components

Status: **proposed** · Date: 2026-05-29 · Branch: `claude/agent-ui-components-research-yXCqL`

## TL;DR

Do **not** adopt Vercel **`json-render`** or Google **`A2UI`** as the primary
mechanism for agent-driven UI. We already have the right primitive in place —
**assistant-ui generative UI (Tool UI) streamed over LangGraph** — and we are
most of the way into the pattern those libraries are selling.

Recommended path, in tiers:

1. **Now (no new deps):** consolidate on the assistant-ui Tools API. Formalize
   the existing per-tool component pattern into a small typed widget registry.
   Migrate off the deprecated `makeAssistantToolUI` toward the `Tools()` API as
   we add widgets.
2. **When we need LLM-*composed* layouts:** borrow the *pattern* from
   `json-render` (catalog + Zod schema + render registry) by implementing a
   single `render_panel`-style tool over our own LangGraph stream — **not** the
   Vercel package.
3. **Watch, don't adopt:** `A2UI`, as a possible long-term portability standard.
   Keeping agent UI intent as declarative JSON in tier 2 keeps that door open.

## Context

- The UI is **Next.js 14 (App Router) + `@assistant-ui/react`** with the
  **`@assistant-ui/react-langgraph`** runtime. Agent traffic is proxied through
  `apps/ui/src/app/api/lg/[..._path]/route.ts`; data fetches hit the FastAPI
  backend directly.
- The agent is **Python + LangChain/LangGraph** (`apps/agent`), not the Vercel
  AI SDK. Tools live in `apps/agent/src/geogent_agent/tools/`.
- Visualization stack already present in `apps/ui`: **deck.gl 9** (+ Development
  Seed geotiff/raster), **MapLibre GL** / `react-map-gl`, **Recharts**, Radix
  primitives, Tailwind, Zod, Zustand.

### We already do agent-driven UI

The repo implements this pattern today, with two mechanisms:

1. **Client tools** (assistant-ui `useAssistantTool`) — the browser executes
   the side effect and returns a structured ack so the model keeps reasoning.
   Defined agent-side in `frontend_actions.py` as `fly_to`, `add_buffer_layer`,
   `list_features_in_viewport`; rendered browser-side under
   `apps/ui/src/components/assistant/tools/` (`FlyToTool`, `BufferLayerTool`,
   `FeaturesInViewportTool`) and registered in `workspace/AssistantPanel.tsx`.
2. **LangGraph `interrupt()` HITL tools** — the graph pauses, the UI renders an
   interactive card, the user acts, and the graph resumes with a result. These
   are `show_sentinel2_scene` (deck.gl COG render) and `confirm_feature_save`
   (`Sentinel2RenderTool`, `ConfirmFeatureSaveTool`, `widgets/ApprovalWidget`).

Live map state (viewport, features, selection, visible layers) is snapshotted
into every agent turn in `assistant/RuntimeProvider.tsx`. Unhandled tool calls
fall back to the generic `assistant-ui/tool-fallback.tsx` renderer.

That **is** generative UI: the LLM selects a typed tool, our React catalog
renders a rich interactive component, and human-in-the-loop is already
supported. This is exactly the architecture both candidate libraries advertise.

## Options evaluated

### Option A — Stay on assistant-ui generative UI  ✅ chosen (tier 1)

Keep the assistant-ui + LangGraph runtime and formalize the existing pattern:
adding an agent-driven visualization = one `@tool` in `frontend_actions.py`
plus one component registered via the Tools API.

- **Pros:** zero new runtime or dependency; reuses our deck.gl/Recharts/Radix
  stack, the `/api/lg` stream, and — critically — our `interrupt()` HITL flow;
  per-tool components are type-safe and individually testable.
- **Cons:** the agent picks from **fixed, hand-built** widgets; it cannot
  compose a novel layout it wasn't pre-programmed for.
- **Note:** `makeAssistantToolUI` is deprecated upstream in favor of the
  `Tools()` API; migrate as the widget set grows.

### Option B — Vercel `json-render`

Define a catalog of components with Zod schemas → the LLM emits a JSON tree
constrained to that catalog → a render registry maps it to React, streamed as
JSONL patches.

- **Pros:** lets the LLM compose **arbitrary dynamic layouts** (e.g. "build a
  dashboard with these four panels"); catalog/patch design is well thought out.
- **Cons:** **coupled to the Vercel AI SDK** (`ai` package: `streamText` /
  `streamObject`, `useUIStream`). Our agent is Python + LangGraph with no
  documented json-render path; adopting it means a parallel Vercel-AI runtime
  or a hand-built bridge from the LangGraph stream into json-render's patch
  format. We would also trade away per-tool type safety and the clean
  `interrupt()` HITL flow.
- **Verdict:** don't take the package. Its core idea (catalog + schema + render
  registry) is worth borrowing natively — see tier 2.

### Option C — Google `A2UI`

An open (Apache-2.0) *protocol*: the agent emits a declarative JSON UI spec
against a client-side catalog of trusted components, designed to cross trust
boundaries safely.

- **Pros:** conceptually the strongest — a portable, framework-agnostic
  standard with an explicit security model.
- **Cons:** **v0.8–0.9 public preview** ("functional but still evolving") and
  **no official React renderer** (Lit, Angular, Flutter only). The React path
  today routes through CopilotKit/AG-UI, which would mean **replacing
  assistant-ui** as our runtime.
- **Verdict:** too early and too React-thin to build production geospatial UI
  on now. Track it.

## Decision

Adopt **Option A now**. Implement **Option B's pattern natively** when we need
LLM-composed layouts. **Track Option C** without building on it.

### Tier 2 sketch (when needed)

Agent — a catalog-style tool alongside the existing ones:

```python
@tool
def render_panel(spec: dict) -> dict:
    """Render a composed UI panel (chart/stat/table) from a validated spec."""
    return {"queued_panel": True, "spec": spec}
```

Browser — `components/assistant/tools/RenderPanelTool.tsx`: validate the spec
with Zod (already a dependency) and map it onto a registry of existing
components.

```tsx
const Registry = { chart: ChartPanel, stat: StatCard, table: FeatureTable };
// useAssistantTool({ toolName: "render_panel", render: ({ args }) =>
//   <PanelRenderer spec={PanelSchema.parse(args.spec)} registry={Registry} /> })
```

This reuses the Recharts/deck.gl/Radix stack, the `/api/lg` stream, and the
HITL pattern — no new runtime. Keeping the agent's UI intent as declarative,
Zod-validated JSON also makes a future mapping onto A2UI cheap if that spec
stabilizes and a solid React renderer lands.

## Consequences

- No new runtime dependency is introduced now; risk stays low.
- New agent-driven visualizations follow a single, documented pattern (one tool
  + one registered component).
- We accept that, until tier 2, the agent can only render pre-built widgets.
- We take on a small migration task: move existing tool UIs from the deprecated
  `makeAssistantToolUI` to the `Tools()` API as the set grows.

## References

- Vercel json-render — <https://github.com/vercel-labs/json-render>,
  <https://json-render.dev/docs/ai-sdk>
- A2UI — <https://github.com/google/A2UI>, <https://a2ui.org/>,
  <https://developers.googleblog.com/introducing-a2ui-an-open-project-for-agent-driven-interfaces/>
- assistant-ui — <https://www.assistant-ui.com/docs/guides/tool-ui>,
  <https://www.assistant-ui.com/docs/guides/Tools>
- Prior art in this repo: `apps/backend/spikes/raster_compute/DECISION.md`
