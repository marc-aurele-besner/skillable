# Stack signals and traps

Load the section for each stack `scripts/detect_stack.py` (or a manual manifest read) reports. Each section says where the important code lives, which defaults to check before reporting something as "missing", and the traps most worth looking for.

---

## Node.js — Express, Fastify, Koa, Hono

- **Where**: `app.(get|post|use)`, `router.*`, `fastify.route`, files under `routes/`, `controllers/`, `api/`, `src/server.*`. Next.js route handlers: `app/**/route.ts`, `pages/api/**`.
- **Defaults to check**: Express has no body size limit beyond `express.json()`'s default `100kb`; no request timeout by default (Node `server.requestTimeout` is 300 s since v18); async errors in Express 4 handlers are **not** caught unless wrapped or using Express 5.
- **Traps**:
  - Unhandled promise rejection in an Express 4 async handler → request hangs until the client times out.
  - `fetch`/axios with no timeout (see checklist section 10).
  - `await` inside `for` loops over DB calls (sequential N+1) or `Promise.all` over thousands of items (connection pool stampede) — bound concurrency (`p-limit`).
  - CPU work on the event loop: `bcrypt` sync variants, big JSON, `zlib` sync, regex on user input (ReDoS).
  - Module-level mutable state used as a per-request store across concurrent requests.
  - `process.on('uncaughtException')` that logs and continues in an undefined state.
  - Serverless (Vercel, Lambda): DB client created per invocation, no pooler; background work after the response is cut off unless using `waitUntil`.

## NestJS

- **Where**: `@Controller`, `@Get/@Post`, `@Resolver`, `@Processor` (BullMQ), `@Cron`, modules in `src/**/**.module.ts`.
- **Defaults to check**: global `ValidationPipe` in `main.ts` (`whitelist`, `forbidNonWhitelisted`, `transform`); global exception filters and interceptors (`app.useGlobal*`); `ClassSerializerInterceptor` with `@Exclude`.
- **Traps**: DTOs without `class-validator` decorators are not validated even with the pipe; `whitelist: false` enables mass assignment; request-scoped providers (`Scope.REQUEST`) cascade and slow every request; `@Cron` runs on every replica; TypeORM `eager: true` relations load everywhere.

## Python — Django / Django REST Framework

- **Where**: `urls.py`, `views.py`, `viewsets`, `serializers.py`, `models.py`, `migrations/`, `tasks.py` (Celery), `settings*.py`.
- **Defaults to check**: `ATOMIC_REQUESTS` (default False); `CONN_MAX_AGE` (default 0 = new connection per request); DRF `DEFAULT_PAGINATION_CLASS` and `PAGE_SIZE` (no pagination by default); `USE_TZ`.
- **Traps**:
  - Serializer `SerializerMethodField` or nested serializers touching relations → N+1 unless the viewset's `get_queryset` uses `select_related`/`prefetch_related`.
  - `ModelSerializer` with `fields = "__all__"` → mass assignment and over-exposure.
  - `get_or_create` without a unique constraint → duplicates.
  - Celery task enqueued inside `atomic()` without `transaction.on_commit`.
  - Migrations: `AddIndex` instead of `AddIndexConcurrently` (needs `atomic = False`); `RunPython` importing models directly instead of `apps.get_model`; `null=False` added to an existing large column.
  - `len(queryset)` / iterating to count instead of `.count()` / `.exists()`; `.all()` on huge tables instead of `.iterator()`.
  - Signals doing heavy or external work synchronously on save.

## Python — FastAPI / Starlette / Flask

- **Where**: `@app.get`, `APIRouter`, `@router.*`, `Depends(...)`; Flask `@app.route`, blueprints.
- **Defaults to check**: Pydantic models on request bodies and `response_model` (filters output); dependency-injected DB sessions and whether they commit/rollback/close.
- **Traps**:
  - `async def` endpoint using a sync driver (`psycopg2`, sync SQLAlchemy session, `requests`) → blocks the event loop. Plain `def` endpoints run in a threadpool and are fine.
  - SQLAlchemy 2.x async: lazy-loaded relationships raise `MissingGreenlet`; need `selectinload`/`joinedload`; `expire_on_commit=True` causes reload queries after commit.
  - Session per request not closed on error → pool exhaustion (`QueuePool limit ... overflow` errors).
  - `BackgroundTasks` used for important work — lost on crash or deploy; use a real queue.
  - Flask global state (`g` misuse, module-level clients not thread-safe under gunicorn threads).
  - Alembic autogenerate migrations reviewed as-is: index creation without `postgresql_concurrently=True` and outside a transaction.

## Go — net/http, chi, gin, echo, fiber

- **Where**: `http.HandleFunc`, `r.Get(...)`, `router.GET`, `e.GET`; `cmd/*/main.go` for wiring; `internal/` for services.
- **Defaults to check**: `http.Server` timeouts (none by default); `sql.DB` pool settings (`SetMaxOpenConns` default unlimited, `SetMaxIdleConns` default 2, `SetConnMaxLifetime`).
- **Traps**:
  - `http.DefaultClient` / `&http.Client{}` with no `Timeout`; response bodies not closed (`defer resp.Body.Close()`) → connection leaks; body not drained → no keep-alive reuse.
  - `ctx` not passed to `QueryContext`/`ExecContext` → cancelled requests keep querying.
  - `rows.Close()` missing or `rows.Err()` unchecked.
  - Goroutines spawned per request with no bound or no cancellation → leaks.
  - Maps shared across goroutines without a mutex (data race; check `go test -race` in CI).
  - GORM: `Preload` missing (N+1), `Save` writes all columns (lost updates on concurrent edits), `AutoMigrate` in production startup.
  - `errors` ignored (`_ =`) on writes and commits.

## Ruby on Rails

- **Where**: `config/routes.rb`, `app/controllers`, `app/models`, `app/serializers` or `app/views/**/*.jbuilder`, `db/migrate`, `db/schema.rb` or `structure.sql`, `app/jobs`, `app/sidekiq`.
- **Defaults to check**: each `save`/`create` is its own transaction; callbacks run inside it; strong params (`permit`); `config.active_record.default_timezone`.
- **Traps**:
  - N+1 in views and serializers — `includes`/`preload`/`eager_load` on the controller query; `strict_loading` or Bullet may already guard.
  - `after_save` callbacks enqueuing jobs or calling APIs → use `after_commit` (or `after_create_commit`); jobs can run before commit otherwise.
  - `validates :email, uniqueness: true` without a unique index → duplicates under concurrency.
  - `find_each` vs `each` on large scopes; `update_all`/`delete_all` skip callbacks and validations (sometimes intentional).
  - Migrations: `add_index` without `algorithm: :concurrently` + `disable_ddl_transaction!`; `remove_column` without `ignored_columns` first; `change_column_null` on large tables. `strong_migrations` gem may already enforce these — check the Gemfile.
  - `default_scope` hiding soft-deleted rows and surprising joins.
  - Sidekiq: arguments must be simple JSON (IDs); `sidekiq_options retry:` defaults to 25 retries over ~21 days.

## Java / Kotlin — Spring Boot

- **Where**: `@RestController`, `@RequestMapping`, `@Service`, `@Repository`, `@Entity`, `@Transactional`, `@Scheduled`, `@KafkaListener`; Flyway `db/migration/V*.sql` or Liquibase changelogs.
- **Traps**: JPA `FetchType.EAGER` and lazy collections in serialized entities (N+1 or `LazyInitializationException`); open-session-in-view (`spring.jpa.open-in-view` default true) hiding N+1s in the view layer; `@Transactional` on private methods or self-invocation (no proxy, no transaction); `@Scheduled` on every replica (ShedLock?); `RestTemplate`/`WebClient` without timeouts; HikariCP pool vs DB max connections.

## PHP — Laravel

- **Where**: `routes/api.php`, `app/Http/Controllers`, `app/Models`, `database/migrations`, `app/Jobs`.
- **Traps**: missing `with()` eager loading (N+1; `Model::preventLazyLoading()` may guard); `$guarded = []` mass assignment; jobs dispatched inside DB transactions without `afterCommit`; `Http::` client without `timeout()`; `->get()` on large tables instead of `chunkById`/`lazy`.

## ORMs and query builders — quick reference

| ORM | Eager load | Transaction | Row lock | Raw / escape hatch | Index declared in |
|-----|-----------|-------------|----------|--------------------|-------------------|
| Prisma | `include` / `select` (separate queries; `relationLoadStrategy: "join"` for joins) | `$transaction([...])` or interactive `$transaction(async tx => ...)` | raw SQL `FOR UPDATE` | `$queryRaw` (safe template) vs `$queryRawUnsafe` (injection risk) | `schema.prisma` `@@index`, `@unique`; SQL in `prisma/migrations` |
| TypeORM | `relations`, `leftJoinAndSelect` | `dataSource.transaction(...)` / `QueryRunner` | `.setLock("pessimistic_write")` | `query()` | `@Index`, migrations |
| Drizzle | `with` in relational queries, joins | `db.transaction(...)` | `.for("update")` | `sql` template | schema `index()`, `drizzle/` migrations |
| Sequelize | `include` | `sequelize.transaction(...)` | `lock: t.LOCK.UPDATE` | `sequelize.query` | model `indexes`, migrations |
| Knex | joins | `knex.transaction(...)` | `.forUpdate()` | `knex.raw` | migrations |
| Mongoose | `populate` (separate queries) | sessions + `withTransaction` (replica set required) | — | aggregation | `schema.index()`; `autoIndex` in prod is a trap |
| SQLAlchemy | `selectinload`, `joinedload`, `subqueryload` | `session.begin()` / `with Session() as s, s.begin()` | `.with_for_update()` | `text()` with bound params | `Index(...)`, `index=True`, Alembic |
| Django ORM | `select_related`, `prefetch_related` | `transaction.atomic()` | `select_for_update()` | `raw()`, `cursor.execute(sql, params)` | `Meta.indexes`, `db_index=True`, migrations |
| ActiveRecord | `includes`, `preload`, `eager_load` | `transaction do ... end` | `lock` / `with_lock` | `find_by_sql`, `sanitize_sql` | `db/schema.rb` / migrations |
| GORM | `Preload`, `Joins` | `db.Transaction(func(tx) ...)` | `Clauses(clause.Locking{Strength: "UPDATE"})` | `Raw` with `?` params | struct tags `gorm:"index"`, migrations |
| sqlc / sqlx / pgx | explicit SQL | `tx, _ := db.BeginTx(ctx, ...)` | SQL | SQL | SQL migrations (goose, migrate, atlas) |

Prisma specifics: `@relation` fields do not create an index on the FK column in PostgreSQL — add `@@index([fkField])` (Prisma warns about this only with `relationMode = "prisma"`). Interactive transactions hold a connection for their whole callback; external calls inside them exhaust the pool.

## Queue and job runners — delivery semantics

| Runner | Delivery | Retry default | Things to check |
|--------|----------|---------------|-----------------|
| Sidekiq | at-least-once | 25 retries, exponential | `after_commit` enqueue, unique jobs gem, dead set monitoring |
| Celery | at-least-once (at-most-once if `acks_late=False` and worker dies) | none unless `autoretry_for`/`retry()` | `acks_late`, `visibility_timeout` (Redis/SQS), `on_commit` enqueue, result backend growth |
| BullMQ | at-least-once | `attempts: 1` unless set | `attempts` + `backoff`, `removeOnComplete`, lock duration vs runtime, stalled jobs |
| SQS | at-least-once (FIFO: exactly-once processing within the dedupe window) | redrive policy | visibility timeout, DLQ `maxReceiveCount`, batch partial failures |
| Kafka | at-least-once typical | consumer-managed | commit after processing, partition key = ordering key, consumer lag alerts |
| RabbitMQ | at-least-once with manual acks | requeue loops | `prefetch`, DLX, ack after processing |
| Go asynq / River | at-least-once | configurable | unique tasks, timeouts, River runs in the DB transaction (outbox-friendly) |
