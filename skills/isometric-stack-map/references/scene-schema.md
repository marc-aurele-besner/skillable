# Scene schema

The renderer in [../assets/stack-map.html](../assets/stack-map.html) draws whatever scene JSON it is given. Write the scene. Never edit the renderer per project. `scripts/build_scene.py` validates the scene and injects it.

## Top level

```json
{
  "title": "acme-shop",
  "subtitle": "pnpm monorepo · Next.js · NestJS · Postgres · SQS",
  "repoUrl": "https://github.com/acme/shop",
  "commit": "3f9c2ab",
  "layers": [], "nodes": [], "links": [], "zones": [], "flows": []
}
```

`repoUrl` and every `url` must be `https://`. The renderer turns anything else into plain text.

## Layers: the tech stack, bottom first

Each layer is one platform. Order is **bottom → top**, so the data tier sits at the bottom and users and clients sit at the top. The viewer lays the layers out as a staircase by default: each tier rises and steps back, so none of them hides another. It can also show them as a straight tower, or flatten them onto one isometric slate with a band per tier.

```json
[{ "id": "data", "label": "Data" }, { "id": "services", "label": "Services" },
 { "id": "apps", "label": "Apps & edge" }, { "id": "clients", "label": "Clients" }]
```

Use 3–5 layers. Typical sets:

| Project shape | Layers (bottom → top) |
|---|---|
| Web app + API + DB | Data · Services · Apps & edge · Users & clients |
| Kubernetes platform | Infra (cluster, ingress, mesh) · Data · Services · Edge · Clients |
| Serverless | Data & storage · Functions · Gateway · Clients |
| Library / monorepo with no runtime | Foundation packages · Core · Adapters · Apps / CLIs |
| Data pipeline | Sources · Ingest · Processing · Storage · Consumers |

## Nodes: components

```json
{ "id": "api", "label": "api", "kind": "service", "layer": "services", "state": "on",
  "tech": ["NestJS 10", "Node 22"], "port": 8080,
  "desc": "REST API for catalog, cart and checkout.",
  "cite": [{ "path": "apps/api/src/main.ts", "line": 12, "url": "https://github.com/acme/shop/blob/3f9c2ab/apps/api/src/main.ts#L12" }] }
```

| Field | Notes |
|---|---|
| `id` | Unique, stable, kebab-case. |
| `label` | Short name as the team says it (≤ 16 chars reads best). |
| `kind` | Picks the glyph (see below). |
| `layer` | A layer id. |
| `state` | `on` glows (part of the default runtime). `idle` is dashed (defined but optional: compose profiles, dev-only, feature-flagged). `off` is grey (deprecated or disabled). `external` is dashed and has no fill (third-party or not in this repo). |
| `tech` | 1–3 chips, most defining first. The first one shows under the label. |
| `port` | Listening port when known. |
| `desc` | One sentence. |
| `cite` | Files that prove the component exists: `{path, line?, url?}` or a plain `"path:line"` string. |
| `tags` | Optional cross-cutting groups (`["checkout", "pci"]`). Each tag becomes a highlight chip in the viewer. |
| `x`, `y`, `size` | Optional overrides. Leave them out and the renderer lays out each layer by neighbour barycenter. `x`/`y` are in grid units (4 ≈ one slot) and scale with the spacing slider. `size` can override `w`, `d`, `h`. |

### Kinds → glyphs

Each kind is drawn as the real-world object people already associate with it:

| kind | drawn as | use for |
|---|---|---|
| `user` | a person | the humans who trigger flows: shoppers, admins, operators |
| `client` | monitor on a stand, terminal on screen | browsers, desktop apps, CLIs |
| `mobile` | smartphone | iOS, Android, React Native and Expo apps |
| `frontend` | monitor showing a web page | SSR/SPA web apps, admin UIs |
| `cdn` | globe on a pedestal | CDNs, DNS, edge networks |
| `gateway` | network switch with ports and antennas | load balancers, ingress, API gateways, reverse proxies |
| `service` | rack-mount server with blade units and LEDs | APIs, backends, monolith processes |
| `worker` | saw-tooth-roof factory with a chimney | queue consumers, cron jobs, schedulers |
| `function` | cube marked with λ | lambdas, edge functions, cloud functions |
| `database` | three stacked disks | SQL/NoSQL databases, search indexes |
| `cache` | memory chip with pins | Redis, Memcached, in-memory stores |
| `storage` | open bucket with hoops | S3/GCS/blob storage, volumes |
| `queue` | tray carrying envelopes | SQS, Kafka topics, RabbitMQ, BullMQ, Pub/Sub |
| `external` | cloud (use `state: "external"`) | Stripe, Auth0, OpenAI, Twilio, SaaS APIs |
| `library` | taped cardboard package | internal packages, when mapping a monorepo's package graph |
| `infra` | full-height rack cabinet | cluster, service mesh, observability stack |

## Links: the network

```json
{ "from": "api", "to": "postgres", "protocol": "SQL", "port": 5432,
  "async": false, "critical": true, "kind": "call", "rate": 1,
  "desc": "Prisma client", "cite": [{ "path": "apps/api/src/db.ts", "line": 4 }] }
```

- **Direction = packet direction = who initiates.** `from` calls `to`.
- `kind`: `call` (default) means `from` depends on `to`. `consume` or `subscribe` means the packets flow `from` producer/queue `to` consumer, but the **consumer** depends on the source. Use this for queue → worker and topic → subscriber.
- `async: true` draws a dashed cable with sparse packets (queues, events, webhooks).
- `critical: false` means the caller keeps working if the target is down (caches with fallbacks, analytics, optional SaaS). It is excluded from failure propagation.
- `rate` scales packet speed (0.5–3). Use it only when the code shows a clear hot path.
- One link per ordered pair. Merge several protocols into one label (`"HTTP + WS"`).

## Zones: network boundaries

Dashed wireframe volumes drawn around their member nodes, across layers:

```json
{ "id": "vpc", "label": "VPC 10.0.0.0/16", "nodes": ["api", "worker", "postgres"] }
```

Use them for VPCs, subnets, Kubernetes clusters and namespaces, Docker networks, and trust boundaries ("PCI scope"). Keep to 3 or fewer. Overlapping zones get hard to read.

## Flows: user actions and what they trigger

A flow is one action and everything it sets off, in order:

```json
{ "id": "checkout", "label": "Checkout", "actor": "shopper", "trigger": "Clicks “Pay now”",
  "steps": [
    { "from": "shopper", "to": "browser", "note": "Submits the checkout form" },
    { "from": "browser", "to": "web", "note": "POST /checkout", "cite": { "path": "apps/web/app/checkout/actions.ts", "line": 18 } },
    { "from": "api", "to": "orders-queue", "note": "Enqueues fulfilment", "async": true }
  ] }
```

| Field | Notes |
|---|---|
| `actor` | Optional node id, usually a `user` node, of who starts the flow. |
| `trigger` | Optional short phrase for the action ("Clicks “Pay now”", "Nightly cron at 02:00", "Stripe sends a webhook"). |
| `color` | Optional `#rrggbb`. The viewer picks a distinct colour when it is omitted. |
| `steps[].async` | Marks a step that the action *kicks off* rather than waits for. The viewer lists these under "Kicks off async". |

Every step must match a link (either direction). Use 2–5 flows of 4–12 steps each, for the actions that matter most: a typical read, a write, a background job, auth, an inbound webhook. To let users trigger flows, give them `user` nodes on the top layer, link them to the clients they use (`"protocol": "uses"`), and start each flow at the user.

## What the viewer lets people change

These are runtime settings in the page. Don't encode them in the scene. Mention them when you hand the map over:

- **Layout:** staircase, tower, or flat slate. Sliders control component spacing, layer height, and layer step-back. Cables can be arcs, right-angle, or straight.
- **Show and hide:** individual layers, component kinds, external and idle components, users and clients, zones, labels, protocol labels, traffic animation, and platforms.
- **Highlight:** any mix of layers, kinds, tags, zones, and statuses. Everything else fades.
- **User flows and actions:** draw each flow as a numbered coloured path, play it step by step, or select it to see what it touches, which third parties it calls, and what async work it kicks off.
- **Themes:** Auto (follows the system), Blueprint, Paper, Neon, Terminal, Arctic, Ember, and Custom (five colour pickers). Settings are saved per scene in the viewer's browser.
