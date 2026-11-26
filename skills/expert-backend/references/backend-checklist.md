# Backend review checklist

Deep checklist behind step 3 of the skill. Each section lists concrete heuristics, where to look, quick grep patterns to find candidates, and what **not** to report. Candidates found here are not findings until they pass the verification gate in SKILL.md step 4.

## How to use this file

1. Load only the sections for the dimensions in scope.
2. Use the grep patterns to find **candidates**, then read the code around each hit. A grep hit is never a finding by itself.
3. For each candidate, write: scenario (input/load/failure → wrong outcome), size (rows, rps), fix (in the project's idiom).
4. Check the "Do not report" list of the section before writing it up.

Grep with `rg` when available (`rg -n --glob '!node_modules' --glob '!vendor' '<pattern>'`), else `grep -rnE`.

---

## 1. API contracts and versioning

| Heuristic | What a real defect looks like |
|-----------|------------------------------|
| Status codes mean what they say | `200 {"error": "not found"}`; `500` for a validation error; `404` vs `403` leaking whether a resource exists to unauthorized callers |
| One error shape | Some routes return `{error}`, others `{message, code}`, framework default HTML on unhandled errors |
| Validate at the boundary | Handler reads `req.body.amount` with no schema; `limit`, `page`, `sort` from the query string passed straight to the ORM; arbitrary `sort` field enables sorting on unindexed or private columns |
| No mass assignment | `User.update(req.body)`, `Model(**payload)`, `params.permit!`, `@Body() dto` without `whitelist: true`, lets clients set `role`, `tenant_id`, `price` |
| Response shaping | ORM entities serialized directly (password hash, internal flags, soft-deleted relations); responses that grow with related data (embedding all comments in a post) |
| Breaking changes | Field renamed or removed, type narrowed (`string` → enum), nullable → required in request, default changed, enum value removed, error code changed, on a public or multi-consumer API without a new version |
| Contract drift | OpenAPI / GraphQL SDL / `.proto` disagrees with the handler (field names, required flags, status codes) |
| Versioning | Public API has no version strategy (URL `/v1`, header, or date-based); internal events have no `version` or `type` field; consumers fail on unknown fields |
| Deprecation | Removed field with no `Deprecation`/`Sunset` header, no `@deprecated` in schema, no changelog |
| Long-running operations | Synchronous endpoint doing work that can take > a few seconds instead of `202 Accepted` + status resource or job |
| Rate limits | Expensive or abusable endpoints (login, password reset, search, export, OTP send) with no limit; `429` without `Retry-After` |

Grep: `req\.body\b|request\.json\(|\*\*request|params\.permit!|update\(req\.body|ValidationPipe|whitelist`.

Do not report: REST purity debates (PUT vs PATCH semantics on an internal API), plural vs singular naming, missing HATEOAS, a single inconsistent route in an otherwise consistent internal API (Low at most).

## 2. Pagination and list endpoints

| Heuristic | Defect |
|-----------|--------|
| Bounded by default | `findMany()` / `.all()` / `SELECT ... FROM orders WHERE user_id = ?` with no `LIMIT`; a client-controlled `limit` with no max (`?limit=1000000`) |
| Offset on big or hot tables | `OFFSET 200000` scans and discards 200k rows; rows inserted between pages shift results (duplicates and skips in feeds), use keyset: `WHERE (created_at, id) < (?, ?) ORDER BY created_at DESC, id DESC LIMIT ?` |
| Stable unique sort | `ORDER BY created_at` alone, ties make page boundaries nondeterministic; add the primary key as tiebreaker |
| Index supports filter + sort | Keyset query needs an index matching `(filter columns..., sort columns...)` |
| Count cost | `COUNT(*)` on every page request of a large table; consider `has_next` via `LIMIT n+1`, estimated counts, or cached totals |
| Cursor opacity | Cursor exposes raw IDs/offsets clients start to construct; cursor not validated (tampered cursor → 500) |
| GraphQL | Connections without `first`/`last` max; nested lists (`users { posts { comments } }`) without depth/complexity limits |

Grep: `OFFSET|\.offset\(|skip:|\.skip\(|\.all\(\)|findMany\(|\.find\(\{\}\)|Paginator|page_size|per_page|limit`.

Do not report: offset pagination on small, bounded tables (admin lists of < ~10k rows), lack of cursors where the UI needs page numbers and the table is modest.

## 3. Idempotency and write safety

| Heuristic | Defect |
|-----------|--------|
| Idempotency keys on side-effecting POST | Mobile client retries `POST /payments` after a timeout → customer charged twice. Fix: `Idempotency-Key` header stored with a unique constraint `(tenant_id, key)` and the stored response replayed |
| Webhook dedupe | Stripe/GitHub/Shopify handler processes the same `event.id` twice (providers retry on any non-2xx or slow response) |
| Webhook speed | Heavy work inline in the webhook handler → provider timeout → redelivery storm. Ack fast, enqueue |
| Signature verification | Signature checked against re-serialized JSON instead of the raw body (always fails, so someone disables it), or not checked at all |
| Check-then-act | `if (!await User.findOne({email})) await User.create(...)` → duplicates under concurrency. Fix: unique index + upsert / `ON CONFLICT DO NOTHING` / catch the unique violation |
| Unique constraint presence | Business rule "one active subscription per user" enforced only in code; partial unique index `WHERE status = 'active'` enforces it |
| Exactly-once claims | Code or docs assume a queue or webhook delivers exactly once |

Grep: `webhook|Idempotency|idempotency_key|event\.id|constructEvent|findOne.*\n.*create|get_or_create|find_or_create_by|upsert|ON CONFLICT`.

Note: Django `get_or_create` and Rails `find_or_create_by` are **not** race-safe without a unique constraint behind them.

## 4. Data modeling

| Heuristic | Defect |
|-----------|--------|
| Constraints in the DB | Required field nullable in the schema; FK relation with no FK constraint (orphans after deletes); uniqueness only in a validator |
| Money | `float`/`double`/JS `number` arithmetic on currency; amounts without a currency column |
| Time | Naive datetimes (`DateTimeField` with `USE_TZ = False`, `timestamp without time zone` storing local time); `Date.now()` vs DB `now()` mixing clocks for ordering |
| IDs | Sequential integer IDs exposed in a public API enabling enumeration of other tenants' resources (pair with authz check); UUIDv4 primary keys on very large, insert-heavy B-tree tables (index fragmentation, UUIDv7/ULID are time-ordered) |
| Enums | Postgres native enum where values change often (`ALTER TYPE ... ADD VALUE` cannot run in a transaction on older versions, removal is hard); string enums without a `CHECK` |
| Multi-tenancy | Table without `tenant_id`, or queries that do not filter on it; unique constraints missing the tenant column (`UNIQUE(email)` instead of `UNIQUE(tenant_id, email)`) |
| Soft delete | Unique constraint not partial; queries/joins that forget `deleted_at IS NULL`; cascades that hard-delete children of a soft-deleted parent |
| JSON columns | Data filtered, joined, or aggregated on lives in JSON without an expression/GIN index; schema-less blobs that every reader must defensively parse |
| Denormalization | Duplicated column with no single writer or reconciliation job → drift |
| Cascades | `ON DELETE CASCADE` from a high-fan-out parent (deleting one account deletes millions of rows in one transaction) |

Do not report: normalization purity, a denormalized read model with a clear owner, naming style.

## 5. Migrations

Check against the engine. PostgreSQL facts (11+ unless noted):

| Operation | Risk | Safe pattern |
|-----------|------|--------------|
| `ADD COLUMN` nullable, no default | Fast (metadata only) |, |
| `ADD COLUMN ... DEFAULT <constant>` | Fast on PG 11+; full rewrite on PG ≤ 10 | Check version |
| `ADD COLUMN ... DEFAULT <volatile>` (`now()`, `gen_random_uuid()`) | Full table rewrite under `ACCESS EXCLUSIVE` | Add nullable, backfill in batches, then set default |
| `SET NOT NULL` | Full scan under `ACCESS EXCLUSIVE` | `ADD CONSTRAINT ... CHECK (col IS NOT NULL) NOT VALID`, `VALIDATE CONSTRAINT`, then `SET NOT NULL` (PG 12+ uses the check) |
| `CREATE INDEX` | Blocks writes for the build | `CREATE INDEX CONCURRENTLY` (outside a transaction: Django `atomic = False` + `AddIndexConcurrently`, Rails `disable_ddl_transaction!` + `algorithm: :concurrently`, Prisma: hand-edit the SQL migration) |
| `ADD FOREIGN KEY` | Locks both tables while validating | `NOT VALID`, then `VALIDATE CONSTRAINT` |
| `ALTER COLUMN TYPE` | Usually a rewrite | New column, dual-write, backfill, swap |
| Rename column/table | Old code breaks instantly mid-deploy | Expand/contract: add new, dual-write, backfill, switch reads, drop old later |
| Drop column | Old code (and ORMs caching column lists, e.g. Rails) breaks mid-deploy | Stop reading/writing first (Rails `ignored_columns`), drop in a later deploy |
| Big `UPDATE`/`DELETE` backfill | Long lock, WAL/replication lag, bloat | Batch by primary key range with commits between batches, ideally in a job not the migration |
| Any DDL | Waits on long-running queries holding locks, then blocks everyone behind it | `SET lock_timeout = '5s'` and retry |

MySQL: prefer `ALGORITHM=INSTANT/INPLACE, LOCK=NONE`; large changes via gh-ost / pt-online-schema-change. SQLite: most `ALTER`s rebuild the table.

Also check: migrations are reversible or explicitly marked irreversible; data migrations do not import live model classes that will change later (Django: use `apps.get_model`); migration order vs code deploy order is safe (code tolerates both schemas during rollout); no `schema.prisma` change without a generated migration; seeds are not mixed into migrations.

Grep: `CREATE INDEX(?! CONCURRENTLY)|add_index|AddIndex|AlterField|change_column|rename_column|RenameField|remove_column|RemoveField|NOT NULL|null=False|\.update_all|UPDATE .* SET`.

Do not report: these risks on tables that are small by evidence (lookup tables, a new table created in the same migration).

## 6. Query efficiency

| Heuristic | Defect |
|-----------|--------|
| N+1 | Loop over parents with a query (or lazy relation access) per item; serializer field that touches a relation; GraphQL resolver per field without DataLoader/batching |
| Missing index | Hot query filters/sorts on columns without an index; FK column without an index (PostgreSQL) used in joins or `ON DELETE` checks |
| Wrong composite order | Index `(created_at, user_id)` for `WHERE user_id = ? ORDER BY created_at` |
| Non-sargable predicates | `WHERE LOWER(email) = ?` without an expression index; `WHERE DATE(created_at) = ?`; `LIKE '%term%'` (needs trigram/full-text) |
| Over-fetching | `SELECT *` of wide rows/blobs for a list view; loading full objects to count (`len(qs)` vs `qs.count()`, `.length` of `findMany`) |
| Loading everything | `.all()` then filtering in application code; exporting a table by loading it into memory instead of streaming/iterating (`iterator()`, `find_each`, cursors) |
| Unbounded `IN` | `WHERE id IN (<10k ids>)` built from user input or another query → use a join or a temporary table |
| Repeated identical queries | The same lookup (current user, tenant settings) executed many times per request without request-scoped memoization |
| Aggregations on the fly | Dashboard computing `SUM` over millions of rows per request → rollup table or materialized view |
| Raw SQL | String-concatenated SQL (injection + no plan reuse) |

Grep: `for .* in .*:\n.*\.(get|filter|objects)|\.forEach\(async|for await|\.map\(async|await .*find.*\)\s*$|\.all\(\)|SELECT \*|LIKE '%|f"SELECT|\$\{.*\}.*(SELECT|WHERE)|raw\(|\$queryRawUnsafe|execute\(f`.

Confirm an N+1 by reading the loop **and** the query construction above it (`select_related`, `includes`, `include`, `joinedload`, `selectinload`, `Preload`). Confirm a missing index by reading every migration or schema index for that table.

Do not report: N+1 bounded by a small constant (≤ ~5 items always); missing indexes on tables that are small by evidence; `SELECT *` on narrow tables.

## 7. Transactions and concurrency

| Heuristic | Defect |
|-----------|--------|
| Atomic multi-write | Order created, then line items inserted in a separate implicit transaction → crash leaves an order with no items |
| External I/O in a transaction | HTTP call to a payment provider while holding row locks → long transactions, pool exhaustion, and the call is not rolled back |
| Lost update | `balance = read(); balance -= x; save(balance)` from two requests → one deduction lost. Fix: `UPDATE accounts SET balance = balance - ? WHERE id = ? AND balance >= ?` and check rows affected; or `SELECT ... FOR UPDATE`; or a `version` column (optimistic locking) |
| Dual write | `db.save(order); queue.publish(OrderCreated)`: crash between them loses or invents events. Fix: transactional outbox, or `transaction.on_commit` / `after_commit` publish with a reconciler |
| Enqueue before commit | Job enqueued inside the transaction runs before commit, reads nothing, fails or no-ops (classic with Sidekiq/Celery/BullMQ) |
| Deadlocks | Two code paths lock the same rows in different orders |
| Isolation assumptions | Code relies on `REPEATABLE READ`/`SERIALIZABLE` behavior while running at the default `READ COMMITTED` (PostgreSQL), or MySQL's `REPEATABLE READ` gap locks surprising the author |
| Long transactions | Transaction wrapping a whole batch job or file processing |
| Distributed locks | Redis `SETNX` lock with no TTL, or with TTL shorter than the work, or released by a non-owner (no token check) |

Grep: `transaction|atomic|\$transaction|BEGIN|on_commit|after_commit|FOR UPDATE|select_for_update|lock\(|SETNX|SET .* NX|Redlock`.

## 8. Caching

| Heuristic | Defect |
|-----------|--------|
| Key completeness | Key `product:{id}` but response varies by locale, currency, or user permissions → wrong data served; key without tenant → cross-tenant leak (Critical) |
| Invalidation | Cache written on read, never invalidated on one of the write paths (admin edit, bulk import, background job) |
| Invalidate-then-write races | Delete cache, then DB write; a concurrent reader repopulates with old data. Prefer write DB then delete key, plus TTL as safety net |
| Stampede | Popular key expires → hundreds of concurrent recomputations hit the DB. Fix: single-flight lock, early probabilistic refresh, stale-while-revalidate, jittered TTL |
| Shared caches and personal data | `Cache-Control: public` or CDN caching on responses with per-user content or `Set-Cookie`; missing `Vary` |
| Cache as source of truth | Data only in Redis with eviction enabled (`allkeys-lru`) or no persistence |
| Failure handling | Redis down → every request 500s instead of falling back to the DB with a short timeout |
| Unbounded memory | In-process `Map`/dict/`lru_cache` without size limit keyed by user input; module-level caches in multi-instance deployments that silently diverge |
| Caching too early | A cache layer on an endpoint that is neither hot nor slow adds invalidation bugs for no benefit, a Note, not a finding, unless it already causes staleness |

Grep: `redis|cache\.(get|set)|@cache|lru_cache|Cache-Control|cache_page|Rails\.cache|memoize|new Map\(\)`.

## 9. Queues and background jobs

| Heuristic | Defect |
|-----------|--------|
| Idempotent handlers | Job sends an email or charges a card and is retried after a crash midway → duplicate side effect. Record completion with a unique key; make each step safe to repeat |
| Retry policy | Infinite retries with no backoff hammering a dead dependency; zero retries on transient errors; retries on non-retryable errors (validation) |
| Dead letters | Failures vanish (no DLQ, no failed-job store, no alert) or one poison message blocks a FIFO queue forever |
| Payloads | Serialized ORM objects or large blobs in the message; pass IDs and re-read |
| Timeouts | SQS visibility timeout / BullMQ lock duration / Celery `visibility_timeout` shorter than job runtime → the same job runs twice concurrently |
| Acks | Celery `acks_late` off on long jobs (lost on worker crash); manual-ack consumers that ack before processing |
| Scheduling | Cron/`setInterval`/APScheduler inside the web process → runs once per instance; no lock or unique job ID |
| Fan-out | One job enqueues millions of child jobs in a loop without batching or rate limits |
| Ordering | Consumers assume FIFO on a queue that does not guarantee it, or partition keys that do not match the entity whose order matters |
| Backpressure | Producer faster than consumers with no queue-depth metric or alert |
| Graceful shutdown | Worker killed on deploy mid-job without `SIGTERM` handling; job not safe to restart |

Grep: `celery|@shared_task|@app\.task|sidekiq|perform_async|perform_later|ActiveJob|bullmq|new Queue\(|new Worker\(|agenda|bee-queue|sqs|SendMessage|kafka|rabbit|amqp|asynq|river|cron|setInterval|schedule`.

## 10. Timeouts, retries, and dependencies

| Heuristic | Defect |
|-----------|--------|
| Outbound timeouts | Node `fetch` has no default timeout (use `AbortSignal.timeout`); Python `requests` has none by default; Go `http.Client{}` and `http.DefaultClient` have none; axios default `0` (none); many SDKs default to 60 s+ |
| Server timeouts | Go `http.Server` without `ReadHeaderTimeout`/`ReadTimeout`/`WriteTimeout` (slowloris); no statement timeout on the DB (`statement_timeout`, `MAX_EXECUTION_TIME`) for request paths |
| Budget ordering | Downstream timeout (30 s) longer than the upstream gateway (10 s) → work continues after the client is gone |
| Retry safety | Retrying non-idempotent POSTs; retrying on 4xx; no jitter (synchronized retry waves); retries at several layers multiplying |
| Circuit breaking | A slow dependency on a hot path with no breaker/bulkhead → all workers stuck waiting, the whole service goes down |
| Pool sizing | `pool_size × instances × workers` > DB `max_connections`; Prisma `connection_limit` default (`num_cpus × 2 + 1`) per instance on serverless; pool exhausted because transactions hold connections across awaits |
| Context propagation | Go handlers that ignore `r.Context()` / do not pass `ctx` to DB calls → cancelled requests keep running |
| Graceful shutdown | No `SIGTERM` handler; readiness not flipped before drain; Kubernetes `terminationGracePeriodSeconds` shorter than the longest request |

Grep: `fetch\(|axios|requests\.(get|post)|httpx|http\.Client|http\.DefaultClient|timeout|retry|backoff|pool_size|connection_limit|max_connections|SIGTERM|Shutdown\(`.

## 11. Scalability limits

| Heuristic | Defect |
|-----------|--------|
| Instance-local state | In-memory sessions, rate limiters, WebSocket room membership, idempotency stores, or caches that must be shared → wrong behavior as soon as there are 2 replicas |
| Event-loop blocking | Sync crypto (`bcrypt.hashSync`, `crypto.pbkdf2Sync`), `fs.*Sync`, large `JSON.parse`/`stringify`, image processing, or sync DB drivers inside Node or Python `async def` handlers |
| Memory buffering | Reading whole uploads/downloads/exports into memory; `res.json(hugeArray)`; no request body size limit |
| Hot rows | Global counter row updated on every request; a single "sequence" row; one tenant's row lock serializing all writes |
| Uploads | Files streamed through app servers instead of signed direct-to-object-storage URLs |
| Per-request fan-out | One request triggers N downstream calls proportional to user data size |
| Search in the primary DB | `ILIKE` full scans for user search on large tables → full-text index or a search engine |
| Abuse | Expensive unauthenticated endpoints with no rate limit or size limit |

Do not report: horizontal-scaling gaps on a service documented or evidently running as a single instance with modest traffic, mention as a Note if growth is planned.

## 12. Observability

| Heuristic | Defect |
|-----------|--------|
| Correlation | No request/trace ID, or it is not passed to downstream calls and enqueued jobs |
| Structured logs | String-concatenated logs in a service that ships to a log platform; inconsistent fields |
| Error logging | Errors logged at every layer (noise) or at none (`catch {}`); stack traces lost by `logger.error(err.message)` |
| Sensitive data | Logging full request bodies, headers (`Authorization`, cookies), tokens, card data, or PII |
| Metrics | No latency/error-rate metrics per endpoint and per job; queue depth not measured |
| Tracing | DB and outbound HTTP calls not instrumented when OpenTelemetry or an APM is otherwise in use |
| Health checks | Liveness depends on the DB (restart storms); readiness missing; health endpoint does expensive work |
| Alerting | No alert definitions in the repo when infra-as-code exists; alerts only on CPU/memory |

Grep: `console\.log|print\(|logger\.|logging\.|pino|winston|structlog|zap|slog|zerolog|opentelemetry|sentry|datadog|newrelic|prometheus|/health|/ready|/live`.

Do not report: absence of a specific vendor; missing tracing in a single small service where logs with request IDs suffice.

## 13. Failure modes

For each dependency on a hot path, fill this table and report the rows with a bad answer:

| Dependency | Slow (p99 × 10) | Down | Returns garbage / unexpected shape |
|------------|-----------------|------|-----------------------------------|
| Primary DB | | | |
| Cache | | | |
| Queue / broker | | | |
| Third-party API | | | |
| Internal service | | | |

Plus:

- **Partial failure** of multi-step workflows (charge succeeded, order write failed): is there compensation, a saga, or a reconciler job that detects and repairs the state?
- **Swallowed errors**: `catch (e) { return { ok: true } }`, `except Exception: pass`, `_ = err` in Go, `rescue => e` with no re-raise or log.
- **Startup coupling**: service refuses to start because an optional dependency (analytics, feature flags) is unreachable.
- **Noisy neighbor**: one tenant's bulk import or export starves others (no per-tenant limits, shared queue without priorities).
- **Retry storms after recovery**: everyone reconnects at once (no jitter on reconnect).
- **Clock and timezone**: jobs scheduled in local time skip or double-run on DST changes.

## Do not report (all dimensions)

- Anything the linter, type checker, or framework already enforces.
- Taste: folder structure, naming, ORM vs raw SQL preference, monolith vs microservices, REST vs GraphQL.
- Scale problems with no evidence of scale.
- "Add tests" without naming the specific risky behavior that is untested.
- Restating what the code does as if it were a finding.
