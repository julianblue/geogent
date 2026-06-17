# ADR 0001: Library choice for agent-driven UI components

Status: **accepted** · Date: 2026-05-30 · Branch: `claude/agent-ui-components-research-yXCqL`

## TL;DR

Do **not** adopt Vercel **`json-render`** or Google **`A2UI`** as the primary
mechanism for agent-driven UI. We already have the right primitive in place —
**assistant-ui generative UI (Tool UI) streamed over LangGraph** — and we are
most of the way into the pattern those libraries are selling.

Chosen path, in tiers:

1. **Done — no new deps:** the assistant-ui Tool UI pattern, formalized into a
   typed widget registry (`components/assistant/widgets/`). Migrate off the
   deprecated `makeAssistantToolUI` toward the `Tools()` API as we add widgets.
2. **Done — built now (this ADR's decision):** a _curated composition layer we
   own_ — the `json-render` _pattern_ (catalog + Zod schema + render registry)
   implemented as a single `render_dashboard` tool over our existing LangGraph
   stream, **not** the Vercel package. The agent composes multiple panels into
   vetted layout templates; it does not emit raw UI. See "Tier 2: implemented".
3. **Watch, don't adopt:** `A2UI`, as a possible long-term portability standard.
   Keeping agent UI intent as declarative, Zod-validated JSON in tier 2 keeps
   that door open at low cost.

### Why build tier 2 now, and why our own thin layer (not A2UI)

The product goal is for the agent to **combine multiple visuals into rich,
composed insights** (agriculture field-health dashboards), and to grow that
catalog over time. That is genuinely beyond tier 1 — selection-only frameworks
(assistant-ui, Vercel AI SDK, CopilotKit) stack widgets vertically but give the
agent no control over _layout/composition_. Only spec-driven approaches (A2UI,
json-render) do.

We deliberately built a **thin composition layer we own** rather than adopting
A2UI/json-render, because for a single flagship app:

- **Quality by construction.** The agent picks from a few vetted, responsive
  layout templates and a curated panel catalog — it can't emit free-form UI, so
  every composition stays on-brand. Adopting a generic renderer reintroduces the
  "wrong-looking generated UI" risk we explicitly want to avoid.
- **The standardized schema is ours and tighter.** A2UI standardizes the
  _layout envelope_, not our _domain data_ — we'd still hand-write every panel's
  data schema. Our Zod panel schemas + the `DashboardSpec` envelope are a fully
  typed, validated contract native to the stack.
- **No dependency on a young, churning spec** and no second runtime. We own
  ~150 lines and keep the `interrupt()` HITL flow and the `/api/lg` stream.
- **Door stays open.** Because panel data schemas are already separated from the
  layout envelope, mapping onto A2UI later (for cross-client interop) is cheap.

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

### Option A — Stay on assistant-ui generative UI ✅ chosen (tier 1)

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

An open (Apache-2.0) _protocol_: the agent emits a declarative JSON UI spec
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

Adopt **Option A** (tier 1, already in place) **and implement Option B's
pattern natively now** (tier 2) — because LLM-composed dashboards are a current
product goal, not a someday-maybe. **Track Option C** without building on it.

### Tier 2: implemented

A single composition tool the agent fills, validated client-side and rendered
through the existing viz primitives inside vetted layout templates.

**Agent** — `tools/frontend_actions.py`: `render_dashboard(spec: DashboardSpec)`,
registered in `tools/__init__.py` and documented in `prompts/system.py`. `spec`
is a Pydantic model (so the LLM gets a real JSON schema): a `layout`
(`stack` | `grid` | `columns`) plus an ordered list of discriminated `panels`
(`stat` | `timeseries` | `histogram` | `table`), data passed inline.

**Browser** — under `components/assistant/widgets/dashboard/`:

- `schema.ts` — the Zod mirror of `DashboardSpec` (the standardized contract).
- `panels.tsx` — `PanelView`, an exhaustive switch mapping each panel type to a
  shared viz primitive (`StatTile`/`TimeSeriesChart`/`Histogram`/`DataTable`).
- `DashboardWidget.tsx` — registered as the `"dashboard"` widget; lays panels
  into the chosen template and gets the inline + promotable workspace views for
  free from the widget framework.
- `tools/RenderDashboardTool.tsx` — `useAssistantTool({ toolName:
"render_dashboard" })`: `safeParse`s the streamed spec and renders
  `<Widget type="dashboard" …>`, degrading to a `ToolErrorChip` on a completed
  invalid spec.

Adding a panel type is a two-file change (extend the union in `schema.ts` and
add a case in `panels.tsx`); adding a whole new widget stays a one-tool +
one-registered-component change. No new runtime; reuses the Recharts/Radix
stack, the `/api/lg` stream, and the `interrupt()` HITL flow.

## Consequences

- No new runtime dependency; risk stays low.
- Two documented patterns: a single-purpose widget (one tool + one registered
  component) and a composed dashboard (fill the `DashboardSpec`).
- The agent can now **compose** multiple visuals into one layout, but only from
  the curated panel catalog and vetted templates — by design.
- The agent-side Pydantic `DashboardSpec` and the browser-side Zod schema must
  be kept in sync (inherent to the Python-agent / TS-UI split).
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
