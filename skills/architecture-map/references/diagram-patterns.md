# Diagram patterns

Diagrams earn their place only when they show the real mechanism, boxes and arrows that match the code. If a diagram would be a list with borders, write the list instead.

## General rules

- **Inline SVG**, hand-laid out, with a `viewBox` and `width="100%"` so it scales. No image exports; no diagram service calls.
- **Theme-aware:** use `currentColor` and CSS custom properties (`stroke: var(--line)`, `fill: var(--surface)`) defined on `:root` and redefined for dark mode, so both themes stay legible. No hard-coded fills.
- **Text is text** (`<text>`), at least 12 px at the rendered size, never baked into paths.
- **One idea per diagram**, ≤ ~12 nodes. Split larger graphs (e.g. a top-level module map plus a zoomed sub-map).
- **Label every edge** with the mechanism: `imports`, `HTTP`, `gRPC`, `queue: orders`, `SQL`, `event: user.created`.
- **Clickable:** wrap nodes in `<a href="#module-x">` to jump to the matching card; give each a `<title>` for hover text.
- **Accessible:** `role="img"` plus `<title>`/`<desc>` summarizing the diagram; the same facts also appear in the text below it.
- **Phone width:** diagrams scroll horizontally inside their own container (`overflow-x: auto`), never the page.

## System context

The system as one box in the center; people on the left; external systems (DB, queue, third-party APIs, auth) on the right and below. Edges labeled with protocol and direction. Mark anything inferred from config but not seen in code with a dashed border.

## Module dependency graph

- Layered left-to-right or top-to-bottom by dependency direction: entry points → application → domain → infrastructure.
- Node size or weight hint from lines of code; edge thickness from import count.
- Cycles: color the participating edges with a warning token and list them below the graph.
- External packages are omitted unless one is central (an ORM, a framework).

## Sequence diagrams (key flows)

- Lifelines for actors and modules only (not every function).
- Numbered steps; each step's label links to the `path:line` that performs it.
- Show async hops (queue, webhook, cron) with a dashed arrow and the channel name.
- Show the failure branch for one important step (validation error, retry, compensation).

## Data model

- Entities as compact boxes with key fields only (id, foreign keys, 2–4 defining fields).
- Crow's-foot or `1`/`*` markers for cardinality.
- Color or group entities by owning module.

## Hotspot chart

A horizontal bar list (not a scatter) of the top 10–15 files by change count, with line count and test presence as small badges. Sort descending; label values directly on the bars.

## Mermaid fallback

When the user wants a Markdown version committed to the repo, translate each diagram to Mermaid (`flowchart LR`, `sequenceDiagram`, `erDiagram`) so it renders on GitHub, and keep the same labels and links.
