#!/usr/bin/env python3
"""Detect a backend's stack so a review starts from facts, not guesses.

Stdlib-only and read-only. Never executes project code, never installs
anything, never connects to a database or the network. Reads manifests and
well-known paths under the given root and prints JSON with:

  - languages and manifests found
  - frameworks, ORMs / query builders, databases, caches, queues / job runners,
    observability libraries (matched from dependency names)
  - migration directories and schema files
  - API contract files (OpenAPI, GraphQL SDL, protobuf)
  - likely route / controller / job locations
  - deploy hints (Dockerfile, serverless, Kubernetes, Procfile)

Usage:
    python3 -I detect_stack.py [root]          # default root: current directory
    python3 -I detect_stack.py services/api --max-files 50000

Exit codes: 0 success, 1 bad input.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

SKIP_DIRS = {
    ".git", "node_modules", "vendor", ".venv", "venv", "env", "__pycache__",
    "dist", "build", ".next", ".nuxt", "target", ".turbo", ".cache", "coverage",
    ".mypy_cache", ".pytest_cache", "tmp", "log", "logs",
}

MANIFESTS = {
    "package.json": "javascript",
    "pyproject.toml": "python",
    "requirements.txt": "python",
    "Pipfile": "python",
    "setup.py": "python",
    "go.mod": "go",
    "Gemfile": "ruby",
    "pom.xml": "java",
    "build.gradle": "java",
    "build.gradle.kts": "kotlin",
    "composer.json": "php",
    "Cargo.toml": "rust",
    "mix.exs": "elixir",
}

# dependency-name substring -> (category, label). Matched case-insensitively
# against dependency tokens in manifests.
SIGNATURES: dict[str, tuple[str, str]] = {
    # frameworks
    "express": ("frameworks", "Express"),
    "@nestjs/core": ("frameworks", "NestJS"),
    "fastify": ("frameworks", "Fastify"),
    "koa": ("frameworks", "Koa"),
    "hono": ("frameworks", "Hono"),
    "next": ("frameworks", "Next.js"),
    "@trpc/server": ("frameworks", "tRPC"),
    "apollo-server": ("frameworks", "Apollo Server"),
    "@apollo/server": ("frameworks", "Apollo Server"),
    "graphql-yoga": ("frameworks", "GraphQL Yoga"),
    "django": ("frameworks", "Django"),
    "djangorestframework": ("frameworks", "Django REST Framework"),
    "fastapi": ("frameworks", "FastAPI"),
    "flask": ("frameworks", "Flask"),
    "starlette": ("frameworks", "Starlette"),
    "litestar": ("frameworks", "Litestar"),
    "strawberry-graphql": ("frameworks", "Strawberry GraphQL"),
    "graphene": ("frameworks", "Graphene"),
    "github.com/gin-gonic/gin": ("frameworks", "Gin"),
    "github.com/go-chi/chi": ("frameworks", "chi"),
    "github.com/labstack/echo": ("frameworks", "Echo"),
    "github.com/gofiber/fiber": ("frameworks", "Fiber"),
    "github.com/gorilla/mux": ("frameworks", "gorilla/mux"),
    "google.golang.org/grpc": ("frameworks", "gRPC"),
    "github.com/99designs/gqlgen": ("frameworks", "gqlgen"),
    "rails": ("frameworks", "Rails"),
    "sinatra": ("frameworks", "Sinatra"),
    "grape": ("frameworks", "Grape"),
    "spring-boot": ("frameworks", "Spring Boot"),
    "laravel/framework": ("frameworks", "Laravel"),
    "symfony/framework-bundle": ("frameworks", "Symfony"),
    "phoenix": ("frameworks", "Phoenix"),
    "axum": ("frameworks", "Axum"),
    "actix-web": ("frameworks", "Actix Web"),
    # ORMs / query builders
    "prisma": ("orms", "Prisma"),
    "@prisma/client": ("orms", "Prisma"),
    "typeorm": ("orms", "TypeORM"),
    "drizzle-orm": ("orms", "Drizzle"),
    "sequelize": ("orms", "Sequelize"),
    "knex": ("orms", "Knex"),
    "kysely": ("orms", "Kysely"),
    "mikro-orm": ("orms", "MikroORM"),
    "mongoose": ("orms", "Mongoose"),
    "sqlalchemy": ("orms", "SQLAlchemy"),
    "sqlmodel": ("orms", "SQLModel"),
    "tortoise-orm": ("orms", "Tortoise ORM"),
    "peewee": ("orms", "Peewee"),
    "alembic": ("migrations_tools", "Alembic"),
    "gorm.io/gorm": ("orms", "GORM"),
    "github.com/jmoiron/sqlx": ("orms", "sqlx"),
    "github.com/jackc/pgx": ("orms", "pgx"),
    "entgo.io/ent": ("orms", "ent"),
    "github.com/pressly/goose": ("migrations_tools", "goose"),
    "github.com/golang-migrate/migrate": ("migrations_tools", "golang-migrate"),
    "ariga.io/atlas": ("migrations_tools", "Atlas"),
    "activerecord": ("orms", "ActiveRecord"),
    "strong_migrations": ("migrations_tools", "strong_migrations"),
    "bullet": ("observability", "Bullet (N+1 detector)"),
    "hibernate": ("orms", "Hibernate/JPA"),
    "spring-boot-starter-data-jpa": ("orms", "Spring Data JPA"),
    "flyway": ("migrations_tools", "Flyway"),
    "liquibase": ("migrations_tools", "Liquibase"),
    "diesel": ("orms", "Diesel"),
    "sqlx-core": ("orms", "sqlx (Rust)"),
    "ecto": ("orms", "Ecto"),
    # databases / drivers
    "pg": ("databases", "PostgreSQL"),
    "postgres": ("databases", "PostgreSQL"),
    "psycopg": ("databases", "PostgreSQL"),
    "asyncpg": ("databases", "PostgreSQL"),
    "mysql": ("databases", "MySQL"),
    "mysql2": ("databases", "MySQL"),
    "pymysql": ("databases", "MySQL"),
    "github.com/go-sql-driver/mysql": ("databases", "MySQL"),
    "sqlite3": ("databases", "SQLite"),
    "better-sqlite3": ("databases", "SQLite"),
    "mongodb": ("databases", "MongoDB"),
    "pymongo": ("databases", "MongoDB"),
    "@neondatabase/serverless": ("databases", "PostgreSQL (Neon)"),
    "@planetscale/database": ("databases", "MySQL (PlanetScale)"),
    "dynamodb": ("databases", "DynamoDB"),
    "cassandra": ("databases", "Cassandra"),
    "elasticsearch": ("databases", "Elasticsearch"),
    "@opensearch-project": ("databases", "OpenSearch"),
    # caches
    "redis": ("caches", "Redis"),
    "ioredis": ("caches", "Redis"),
    "@upstash/redis": ("caches", "Redis (Upstash)"),
    "github.com/redis/go-redis": ("caches", "Redis"),
    "memcache": ("caches", "Memcached"),
    "django-redis": ("caches", "Redis"),
    "lru-cache": ("caches", "in-process LRU"),
    "node-cache": ("caches", "in-process cache"),
    "cachetools": ("caches", "in-process cache"),
    # queues / jobs
    "bullmq": ("queues", "BullMQ"),
    "bull": ("queues", "Bull"),
    "bee-queue": ("queues", "Bee-Queue"),
    "agenda": ("queues", "Agenda"),
    "pg-boss": ("queues", "pg-boss"),
    "graphile-worker": ("queues", "Graphile Worker"),
    "inngest": ("queues", "Inngest"),
    "@trigger.dev": ("queues", "Trigger.dev"),
    "node-cron": ("queues", "node-cron (in-process cron)"),
    "@nestjs/schedule": ("queues", "@nestjs/schedule (in-process cron)"),
    "celery": ("queues", "Celery"),
    "rq": ("queues", "RQ"),
    "dramatiq": ("queues", "Dramatiq"),
    "huey": ("queues", "Huey"),
    "arq": ("queues", "arq"),
    "apscheduler": ("queues", "APScheduler (in-process cron)"),
    "sidekiq": ("queues", "Sidekiq"),
    "good_job": ("queues", "GoodJob"),
    "solid_queue": ("queues", "Solid Queue"),
    "delayed_job": ("queues", "Delayed Job"),
    "resque": ("queues", "Resque"),
    "github.com/hibiken/asynq": ("queues", "asynq"),
    "github.com/riverqueue/river": ("queues", "River"),
    "kafkajs": ("queues", "Kafka"),
    "confluent-kafka": ("queues", "Kafka"),
    "github.com/segmentio/kafka-go": ("queues", "Kafka"),
    "amqplib": ("queues", "RabbitMQ"),
    "pika": ("queues", "RabbitMQ"),
    "@aws-sdk/client-sqs": ("queues", "SQS"),
    "boto3": ("queues", "AWS SDK (SQS/SNS possible)"),
    "nats": ("queues", "NATS"),
    "temporalio": ("queues", "Temporal"),
    "@temporalio": ("queues", "Temporal"),
    # observability / resilience
    "@opentelemetry": ("observability", "OpenTelemetry"),
    "opentelemetry": ("observability", "OpenTelemetry"),
    "go.opentelemetry.io": ("observability", "OpenTelemetry"),
    "@sentry": ("observability", "Sentry"),
    "sentry-sdk": ("observability", "Sentry"),
    "sentry-ruby": ("observability", "Sentry"),
    "dd-trace": ("observability", "Datadog"),
    "ddtrace": ("observability", "Datadog"),
    "newrelic": ("observability", "New Relic"),
    "prom-client": ("observability", "Prometheus"),
    "prometheus": ("observability", "Prometheus"),
    "pino": ("observability", "pino (structured logs)"),
    "winston": ("observability", "winston"),
    "structlog": ("observability", "structlog"),
    "go.uber.org/zap": ("observability", "zap"),
    "github.com/rs/zerolog": ("observability", "zerolog"),
    "lograge": ("observability", "lograge"),
    "opossum": ("resilience", "opossum (circuit breaker)"),
    "cockatiel": ("resilience", "cockatiel"),
    "p-retry": ("resilience", "p-retry"),
    "tenacity": ("resilience", "tenacity"),
    "github.com/sony/gobreaker": ("resilience", "gobreaker"),
    "resilience4j": ("resilience", "Resilience4j"),
    "express-rate-limit": ("resilience", "express-rate-limit"),
    "@nestjs/throttler": ("resilience", "@nestjs/throttler"),
    "rack-attack": ("resilience", "rack-attack"),
    "slowapi": ("resilience", "slowapi"),
}

# Short names that are only matched as an exact dependency token.
# Names whose real packages come with suffixes (psycopg2-binary,
# spring-boot-starter-web, sentry-sdk[fastapi]) and are matched as prefixes.
PREFIX_OK = {"psycopg", "spring-boot", "hibernate", "flyway", "liquibase", "opentelemetry", "prometheus", "elasticsearch", "memcache", "apollo-server", "dynamodb", "cassandra", "mikro-orm"}

EXACT_ONLY = {"pg", "rq", "arq", "bull", "koa", "next", "nats", "postgres", "mysql", "redis", "rails", "grape", "huey", "knex", "agenda", "pino"}

MIGRATION_DIR_NAMES = {"migrations", "migrate", "db/migrate", "prisma/migrations", "alembic/versions", "drizzle", "db/migration", "database/migrations"}
SCHEMA_FILES = ("schema.prisma", "schema.rb", "structure.sql", "schema.sql", "drizzle.config.ts", "drizzle.config.js", "alembic.ini", "ormconfig.json", "ormconfig.ts", "atlas.hcl", "sqlc.yaml", "sqlc.yml")
CONTRACT_PATTERNS = (
    re.compile(r"(openapi|swagger)[^/]*\.(ya?ml|json)$", re.I),
    re.compile(r"\.(graphql|gql)$", re.I),
    re.compile(r"\.proto$", re.I),
    re.compile(r"asyncapi[^/]*\.(ya?ml|json)$", re.I),
)
ROUTE_HINT_RE = re.compile(
    r"(^|/)(routes?|controllers?|handlers?|api|views|viewsets|resolvers|endpoints|routers?)(/|\.|$)|urls\.py$|routes\.rb$|route\.(t|j)s$",
    re.I,
)
JOB_HINT_RE = re.compile(r"(^|/)(jobs?|workers?|tasks?|queues?|consumers?|processors?|cron|schedulers?)(/|\.|$)|tasks\.py$", re.I)
DEPLOY_FILES = ("Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yaml", "Procfile", "fly.toml", "render.yaml", "vercel.json", "netlify.toml", "serverless.yml", "serverless.ts", "app.yaml", "wrangler.toml", "railway.json", "template.yaml", "Chart.yaml", "kustomization.yaml")

DEP_TOKEN_RE = re.compile(r"[A-Za-z0-9@][A-Za-z0-9@._/\-]*")
MAX_MANIFEST_BYTES = 2_000_000


def read_text(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_MANIFEST_BYTES:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def dependency_tokens(path: Path) -> set[str]:
    text = read_text(path)
    if not text:
        return set()
    if path.name == "package.json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return set()
        tokens: set[str] = set()
        for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            section = data.get(key) or {}
            if isinstance(section, dict):
                tokens.update(k.lower() for k in section)
        return tokens
    if path.name == "composer.json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return set()
        tokens = set()
        for key in ("require", "require-dev"):
            section = data.get(key) or {}
            if isinstance(section, dict):
                tokens.update(k.lower() for k in section)
        return tokens
    tokens = set()
    for raw in DEP_TOKEN_RE.findall(dependency_text(path.name, text)):
        token = raw.lower().strip("./")
        tokens.add(token)
        # python extras / version pins: "sqlalchemy[asyncio]>=2" -> sqlalchemy
        tokens.add(re.split(r"[\[<>=~!;]", token)[0])
    return tokens


def _toml_dependency_names(text: str) -> list[str] | None:
    """Dependency names from pyproject.toml / Pipfile / Cargo.toml, or None without tomllib."""
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        return None
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []
    names: list[str] = []

    def add_specs(specs) -> None:
        if isinstance(specs, list):
            names.extend(x for x in specs if isinstance(x, str))
        elif isinstance(specs, dict):
            names.extend(str(k) for k in specs)

    project = data.get("project") or {}
    add_specs(project.get("dependencies"))
    for group in (project.get("optional-dependencies") or {}).values():
        add_specs(group)
    for group in (data.get("dependency-groups") or {}).values():
        add_specs(group)
    poetry = (data.get("tool") or {}).get("poetry") or {}
    add_specs(poetry.get("dependencies"))
    add_specs(poetry.get("dev-dependencies"))
    for group in (poetry.get("group") or {}).values():
        if isinstance(group, dict):
            add_specs(group.get("dependencies"))
    for key in ("packages", "dev-packages", "dependencies", "dev-dependencies", "build-dependencies"):
        add_specs(data.get(key))  # Pipfile and Cargo.toml
    return names


def dependency_text(name: str, text: str) -> str:
    """Keep only the parts of a manifest that name dependencies.

    Matching every word of a manifest turns prose (descriptions, project
    names, comments) into false framework hits, so each format is narrowed
    to its dependency declarations.
    """
    if name in {"pyproject.toml", "Pipfile", "Cargo.toml"}:
        names = _toml_dependency_names(text)
        return text if names is None else "\n".join(names)
    if name == "setup.py":
        return "\n".join(re.findall(r"""['"]([A-Za-z0-9_.\-\[\]]+\s*(?:[<>=~!][^'"]*)?)['"]""", text))
    if name.startswith("requirements"):
        lines = []
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if line and not line.startswith("-"):
                lines.append(line.split()[0])
        return "\n".join(lines)
    if name == "Gemfile":
        return "\n".join(re.findall(r"""^\s*gem\s+['"]([^'"]+)['"]""", text, re.M))
    if name == "go.mod":
        return "\n".join(re.findall(r"^\s*(?:require\s+)?([\w.\-]+\.[a-z]{2,}/\S+)\s+v\d", text, re.M))
    if name == "pom.xml":
        return "\n".join(re.findall(r"<(?:artifactId|groupId)>\s*([^<\s]+)\s*</", text))
    if name.startswith("build.gradle"):
        return "\n".join(re.findall(r"""['"]([\w.\-]+:[\w.\-]+)(?::[^'"]*)?['"]""", text))
    if name == "mix.exs":
        return "\n".join(re.findall(r"\{:(\w+)\s*,", text))
    return text


def match_signatures(tokens: set[str]) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for sig, (category, label) in SIGNATURES.items():
        if sig in EXACT_ONLY:
            hit = sig in tokens
        elif sig in PREFIX_OK:
            hit = any(t.startswith(sig) for t in tokens)
        else:
            # exact name, a scoped sub-package (@sentry/node), or a Go module
            # major-version path (github.com/go-chi/chi/v5)
            hit = any(t == sig or t.startswith(sig + "/") for t in tokens)
        if hit:
            found.setdefault(category, set()).add(label)
    return found


def walk(root: Path, max_files: int):
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            count += 1
            if count > max_files:
                return
            yield Path(dirpath) / name


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", nargs="?", default=".", help="repository or service directory")
    parser.add_argument("--max-files", type=int, default=20000, help="stop walking after this many files")
    parser.add_argument("--max-list", type=int, default=40, help="max paths listed per category")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(json.dumps({"error": f"not a directory: {args.root}"}))
        return 1

    result: dict[str, object] = {"root": str(root)}
    categories: dict[str, set[str]] = {}
    languages: set[str] = set()
    manifests: list[str] = []
    migrations: set[str] = set()
    schemas: list[str] = []
    contracts: list[str] = []
    routes: list[str] = []
    jobs: list[str] = []
    deploy: list[str] = []
    truncated = False

    file_count = 0
    for path in walk(root, args.max_files):
        file_count += 1
        rel = path.relative_to(root).as_posix()
        name = path.name
        if name in MANIFESTS:
            languages.add(MANIFESTS[name])
            manifests.append(rel)
            for cat, labels in match_signatures(dependency_tokens(path)).items():
                categories.setdefault(cat, set()).update(labels)
        elif name.startswith("requirements") and name.endswith(".txt"):
            languages.add("python")
            manifests.append(rel)
            for cat, labels in match_signatures(dependency_tokens(path)).items():
                categories.setdefault(cat, set()).update(labels)
        parent = path.parent.relative_to(root).as_posix()
        padded = "/" + parent + "/"
        for mdir in MIGRATION_DIR_NAMES:
            idx = padded.find("/" + mdir + "/")
            if idx != -1:
                migrations.add((padded[: idx + len(mdir) + 1]).strip("/"))
                break
        if name in SCHEMA_FILES:
            schemas.append(rel)
        if any(p.search(rel) for p in CONTRACT_PATTERNS):
            contracts.append(rel)
        if path.suffix in {".ts", ".js", ".mjs", ".py", ".go", ".rb", ".java", ".kt", ".php", ".ex", ".rs"} and "test" not in rel.lower() and "spec" not in rel.lower():
            if ROUTE_HINT_RE.search(rel):
                routes.append(rel)
            if JOB_HINT_RE.search(rel):
                jobs.append(rel)
        if name in DEPLOY_FILES or rel.startswith(("k8s/", "kubernetes/", "helm/", "deploy/", "infra/", "terraform/")):
            deploy.append(rel)
    if file_count >= args.max_files:
        truncated = True

    def cap(items):
        items = sorted(set(items))
        return items[: args.max_list] + ([f"... {len(items) - args.max_list} more"] if len(items) > args.max_list else [])

    result["languages"] = sorted(languages)
    result["manifests"] = cap(manifests)
    for cat in ("frameworks", "orms", "migrations_tools", "databases", "caches", "queues", "observability", "resilience"):
        result[cat] = sorted(categories.get(cat, set()))
    result["migration_dirs"] = cap(migrations)
    result["schema_files"] = cap(schemas)
    result["api_contracts"] = cap(contracts)
    result["route_files"] = cap(routes)
    result["job_files"] = cap(jobs)
    result["deploy_files"] = cap(deploy)
    result["files_scanned"] = file_count
    result["truncated"] = truncated
    result["note"] = "Dependency matches are hints from manifest names; confirm each in the code before relying on it."
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
