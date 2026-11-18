#!/usr/bin/env python3
"""List candidate application-security leads in a web project.

A starting point for the expert-appsec review, not a scanner verdict. It walks
the project's source files and prints:

  - the detected stack (frameworks found in manifests)
  - an inventory of likely entry points (routes, handlers, server actions)
  - candidate sinks, risky config, and secrets grouped by category

Every hit is a LEAD to trace from source to sink; most will be safe. Secrets
are always redacted in the output.

    python3 -I scripts/appsec_scan.py <repo-root>
    python3 -I scripts/appsec_scan.py <repo-root> --json
    python3 -I scripts/appsec_scan.py <repo-root> --focus injection,xss,secrets
    python3 -I scripts/appsec_scan.py --headers https://app.example.com

--headers sends ONE GET request with no cookies or credentials and reports the
security headers and Set-Cookie flags. Use it only on a URL the user owns.

Stdlib only, Python 3.8+. Read-only: it never writes to the project, never
executes project code, and makes no network request unless --headers is given.

Exit codes:
  0  scan completed (leads may be present)
  1  usage error
  2  the --headers request failed
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

SKIP_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build", "out", ".next", ".nuxt",
    ".svelte-kit", ".output", ".turbo", ".vercel", ".cache", "coverage",
    "__pycache__", ".venv", "venv", "env", "target", ".gradle", ".idea",
    ".pytest_cache", ".mypy_cache", "bower_components", "public/build",
}
SOURCE_EXT = {
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte", ".astro",
    ".py", ".rb", ".erb", ".php", ".go", ".java", ".kt", ".cs", ".html",
    ".jinja", ".j2", ".twig", ".hbs", ".ejs", ".pug", ".rules",
    ".json", ".toml", ".yaml", ".yml", ".conf", ".env", ".tf",
}
SKIP_FILES = {
    "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb",
    "poetry.lock", "Pipfile.lock", "Gemfile.lock", "composer.lock", "go.sum",
    "Cargo.lock",
}
MAX_FILE_BYTES = 1_000_000
MAX_HITS_PER_RULE = 40

# (category, rule id, regex, note). Patterns aim for recall; the review decides.
RULES = [
    # Injection
    ("injection", "sql-interpolation",
     r"""(?i)\b(select|insert|update|delete)\b[^;\n]{0,120}(\$\{|"\s*\+\s*\w|'\s*\+\s*\w|%s|\{\w+\}|#\{)""",
     "SQL built from strings; confirm parameterization"),
    ("injection", "orm-raw",
     r"""\$queryRawUnsafe|\$executeRawUnsafe|Prisma\.raw\(|sequelize\.literal|\.raw\(|\.extra\(|RawSQL\(|\btext\(\s*f["']|whereRaw|orderByRaw|DB::raw|createNativeQuery|\.query\(\s*`""",
     "ORM raw-query escape hatch"),
    ("injection", "nosql-operator",
     r"""\$where|\.find(One)?\(\s*req\.(body|query)""",
     "Mongo query from request object; check type casting"),
    ("injection", "shell",
     r"""child_process|\bexec(Sync)?\(\s*[`'"]?[^)]*(\$\{|\+)|shell\s*=\s*True|os\.system\(|os\.popen\(|subprocess\.(call|run|Popen)\([^)]*shell|Runtime\.getRuntime\(\)\.exec|exec\.Command\(\s*"(ba)?sh"\s*,\s*"-c\"""",
     "Process execution; confirm no shell and argument arrays"),
    ("injection", "eval",
     r"""\beval\(|new Function\(|vm\.run(InNewContext|InContext|InThisContext)|setTimeout\(\s*["'`]|\bexec\(\s*(request|req|params|input)""",
     "Dynamic code evaluation"),
    ("injection", "ssti",
     r"""render_template_string\(|Template\(\s*(request|req|params|input)|\.compile\(\s*(req|request|params|body)|Handlebars\.compile\(|ejs\.render\(|pug\.render\(""",
     "Template compiled at runtime; check the template source"),
    ("injection", "deserialization",
     r"""pickle\.loads?\(|yaml\.load\((?![^)]*SafeLoader)|\bunserialize\(|Marshal\.load|ObjectInputStream|enableDefaultTyping|JsonTypeInfo\.Id\.CLASS|node-serialize""",
     "Unsafe deserialization"),
    ("injection", "path-traversal",
     r"""(path\.join|path\.resolve|os\.path\.join|filepath\.Join|send_file|sendFile|res\.download|readFile(Sync)?|open)\([^)]*(req\.|request\.|params|query|args\[)""",
     "File path built from request data"),
    # XSS
    ("xss", "raw-html",
     r"""dangerouslySetInnerHTML|v-html|\[innerHTML\]|\{@html|\|\s*safe\b|mark_safe\(|\.html_safe|\braw\(|\{!!|th:utext|bypassSecurityTrust|template\.HTML\(""",
     "Escaping disabled; trace what flows in"),
    ("xss", "dom-sink",
     r"""\.innerHTML\s*=|\.outerHTML\s*=|insertAdjacentHTML|document\.write\(|\.html\(\s*[a-zA-Z_$]""",
     "DOM HTML sink"),
    ("xss", "inline-json",
     r"""<script[^>]*>[^<]*JSON\.stringify""",
     "JSON inlined into a script tag; needs </script> escaping"),
    ("xss", "markdown-html",
     r"""html\s*:\s*true|sanitize\s*:\s*false|allowDangerousHtml""",
     "Markdown/HTML renderer with raw HTML enabled"),
    # Auth and sessions
    ("auth", "jwt-decode",
     r"""jwt\.decode\(|algorithms\s*[:=]\s*\[[^\]]*none|verify\s*=\s*False|ignoreExpiration\s*:\s*true""",
     "JWT read without full verification"),
    ("auth", "weak-hash",
     r"""(?i)(md5|sha1)\s*\(|createHash\(\s*['"](md5|sha1)['"]|hashlib\.(md5|sha1)\(""",
     "Weak hash; matters only for passwords or tokens"),
    ("auth", "insecure-random",
     r"""Math\.random\(\)|\brandom\.(random|randint|choice)\(|rand\(\)""",
     "Non-CSPRNG; matters only for tokens, ids, or secrets"),
    ("auth", "cookie-flags",
     r"""(?i)(httpOnly|secure)\s*[:=]\s*false|SESSION_COOKIE_SECURE\s*=\s*False|SameSite\s*[:=]\s*['"]?none""",
     "Session cookie hardening disabled"),
    ("auth", "open-redirect",
     r"""(redirect|redirect_to|res\.redirect|location\.href\s*=|window\.location\s*=)\(?\s*(req\.|request\.|params|searchParams|query)""",
     "Redirect target from request data"),
    # Authorization
    ("authz", "find-by-request-id",
     r"""find(Unique|First|ById|One|_by)?\(\s*\{?\s*(where\s*:\s*\{\s*)?id\s*:\s*(req\.|params|args|input)|findById\(\s*req\.params|get_object_or_404\([^)]*pk\s*=|\.get\(\s*id\s*=\s*(request|kwargs)""",
     "Object fetched by request id; confirm owner/tenant scoping"),
    ("authz", "mass-assignment",
     r"""\.(update|create|save|insert)\(\s*(req\.body|request\.(json|data|POST)|params)\s*\)|permit!|\$guarded\s*=\s*\[\s*\]|fields\s*=\s*['"]__all__['"]""",
     "Whole request body written to a model"),
    ("authz", "allow-any",
     r"""AllowAny|permitAll\(\)|@csrf_exempt|allow read, write: if true|using\s*\(\s*true\s*\)|@Public\(\)""",
     "Explicit open access; confirm it is intended"),
    # CSRF
    ("csrf", "csrf-disabled",
     r"""csrf\(\)\.disable|csrf\.disable|skip_forgery_protection|protect_from_forgery\s+with:\s*:null_session|VerifyCsrfToken|checkOrigin\s*:\s*false|CSRF_ENABLED\s*=\s*False""",
     "CSRF protection disabled or exempted"),
    ("csrf", "state-changing-get",
     r"""(app|router)\.get\(\s*['"][^'"]*(delete|remove|logout|update|approve|transfer|confirm)""",
     "GET route name suggests a side effect"),
    # SSRF
    ("ssrf", "outbound-from-request",
     r"""(fetch|axios(\.\w+)?|got|request|http\.get|https\.get|requests\.(get|post)|httpx\.(get|post)|urlopen|http\.Get|RestTemplate|WebClient)\(\s*(req\.|request\.|params|body|query|input|url\b)""",
     "Outbound request to a URL that may be user-supplied"),
    ("ssrf", "tls-disabled",
     r"""rejectUnauthorized\s*:\s*false|verify\s*=\s*False|InsecureSkipVerify\s*:\s*true|NODE_TLS_REJECT_UNAUTHORIZED""",
     "TLS verification disabled"),
    ("ssrf", "image-proxy-wildcard",
     r"""hostname\s*:\s*['"]\*\*['"]""",
     "Image optimizer allows any remote host"),
    # CORS
    ("cors", "cors-reflect",
     r"""origin\s*:\s*(true|\*|['"]\*['"])|Access-Control-Allow-Origin['"]?\s*[,:]\s*(req|request)\.|allow_origins\s*=\s*\[\s*['"]\*['"]|AllowAllOrigins|endsWith\(\s*['"][a-z0-9.-]+\.[a-z]+['"]\s*\)""",
     "Broad or reflected CORS origin; dangerous with credentials"),
    # Headers and config
    ("headers", "header-config",
     r"""helmet\(|Content-Security-Policy|Strict-Transport-Security|SECURE_HSTS_SECONDS|frame-ancestors|X-Frame-Options""",
     "Where headers are set (inventory, not a finding)"),
    ("headers", "debug-on",
     r"""(?i)\bDEBUG\s*=\s*True\b|APP_DEBUG\s*=\s*true|app\.run\([^)]*debug\s*=\s*True|productionBrowserSourceMaps\s*:\s*true|sourcemap\s*:\s*true|management\.endpoints\.web\.exposure\.include\s*=\s*\*""",
     "Debug mode, source maps, or actuator exposure"),
    ("headers", "trust-proxy",
     r"""trust proxy['"]?\s*,\s*true|X-Forwarded-For""",
     "Client IP from a forwarded header; check proxy trust"),
    # Secrets (code patterns; literal credentials are matched by SECRET_RULES)
    ("secrets", "fallback-secret",
     r"""(?i)(env(iron)?(\.get)?[\[\(.]\s*['"]?\w*(SECRET|KEY|TOKEN|PASSWORD)\w*['"]?[\]\)]?\s*(\|\||\?\?|or)\s*['"][^'"]+['"])|getenv\(\s*['"]\w*(SECRET|KEY|TOKEN|PASSWORD)\w*['"]\s*,\s*['"][^'"]+['"]""",
     "Hardcoded fallback for a secret; production may fall through"),
    ("secrets", "static-root",
     r"""express\.static\(\s*['"]\.?/?['"]|express\.static\(\s*__dirname\s*\)""",
     "Static server rooted at the project; may serve .env or .git"),
    # Upload
    ("upload", "upload-handler",
     r"""multer\(|upload\.(single|array|fields)|request\.FILES|UploadFile|MultipartFile|move_uploaded_file|createPresignedPost|getSignedUrl|formidable|busboy""",
     "File upload entry point; check type, size, name, and serving origin"),
    # Rate limiting
    ("ratelimit", "limiter",
     r"""rateLimit\(|express-rate-limit|@Throttle|Flask-Limiter|slowapi|rack-attack|Rack::Attack|throttle\(|Ratelimit\(""",
     "Rate limiter in use (inventory; confirm coverage of auth routes)"),
    # Logging
    ("logging", "sensitive-log",
     r"""(?i)(console\.(log|info|debug)|logger\.\w+|log\.\w+|print)\([^)]*(password|passwd|secret|token|authorization|cookie|req\.body|request\.body|ssn|card)""",
     "Possible sensitive data written to logs"),
    ("logging", "error-leak",
     r"""err\.stack|traceback\.format_exc|e\.printStackTrace|sendDefaultPii\s*:\s*true""",
     "Stack traces or PII possibly sent to clients or trackers"),
]

SECRET_RULES = [
    ("aws-access-key", r"\bAKIA[0-9A-Z]{16}\b"),
    ("github-token", r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{40,}"),
    ("stripe-secret", r"\b(sk|rk)_live_[A-Za-z0-9]{16,}"),
    ("slack-token", r"\bxox[abpors]-[A-Za-z0-9-]{10,}"),
    ("google-api-key", r"\bAIza[0-9A-Za-z_-]{35}\b"),
    ("openai-style-key", r"\bsk-(proj-)?[A-Za-z0-9_-]{32,}"),
    ("anthropic-key", r"\bsk-ant-[A-Za-z0-9_-]{20,}"),
    ("private-key", r"-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
    ("db-url-with-password", r"\b(postgres(ql)?|mysql|mongodb(\+srv)?|redis|amqp)://[^:\s/'\"]+:[^@\s'\"]{3,}@"),
    ("jwt", r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    ("supabase-service-role", r"(?i)service_role"),
    ("generic-assignment",
     r"""(?i)\b(api[_-]?key|secret|password|passwd|private[_-]?key|access[_-]?token|client[_-]?secret)\b\s*[:=]\s*['"][^'"\s]{12,}['"]"""),
    ("client-prefixed-secret",
     r"""\b(NEXT_PUBLIC|VITE|REACT_APP|PUBLIC|NUXT_PUBLIC|EXPO_PUBLIC)_[A-Z0-9_]*(SECRET|PRIVATE|SERVICE_ROLE|PASSWORD|TOKEN)[A-Z0-9_]*"""),
]

PLACEHOLDER_RE = re.compile(r"(?i)(example|placeholder|changeme|your[_-]|xxx+|dummy|<[^>]+>|\$\{|process\.env|os\.environ|getenv)")

ROUTE_RULES = [
    ("express/fastify", r"""\b(app|router|server|fastify)\.(get|post|put|patch|delete|all|route)\(\s*['"`]([^'"`]+)"""),
    ("nest", r"""@(Get|Post|Put|Patch|Delete)\(\s*['"]?([^'")]*)"""),
    ("flask/fastapi", r"""@\w+\.(route|get|post|put|patch|delete)\(\s*['"]([^'"]+)"""),
    ("django", r"""\b(re_)?path\(\s*r?['"]([^'"]*)['"]"""),
    ("rails", r"""^\s*(get|post|put|patch|delete|resources?)\s+['":]([\w/:]+)"""),
    ("laravel", r"""Route::(get|post|put|patch|delete|any|resource)\(\s*['"]([^'"]+)"""),
    ("spring", r"""@(Get|Post|Put|Patch|Delete|Request)Mapping\(\s*(value\s*=\s*)?["']?([^"')]*)"""),
    ("go", r"""\.(HandleFunc|Handle|GET|POST|PUT|PATCH|DELETE)\(\s*"([^"]+)"""),
    ("server-action", r"""^\s*['"]use server['"]"""),
]

FILE_ROUTE_PATTERNS = [
    ("next-route-handler", re.compile(r"(^|/)app/(.+/)?route\.(t|j)sx?$")),
    ("next-pages-api", re.compile(r"(^|/)pages/api/.+\.(t|j)sx?$")),
    ("sveltekit-endpoint", re.compile(r"(^|/)src/routes/(.+/)?\+server\.(t|j)s$")),
    ("sveltekit-form-action", re.compile(r"(^|/)src/routes/(.+/)?\+page\.server\.(t|j)s$")),
    ("nuxt-server-route", re.compile(r"(^|/)server/(api|routes)/.+\.(t|j)s$")),
    ("netlify-function", re.compile(r"(^|/)netlify/functions/.+")),
    ("cloudflare-function", re.compile(r"(^|/)functions/.+\.(t|j)s$")),
    ("graphql-resolver", re.compile(r"resolvers?(/|\.)")),
]

STACK_MARKERS = {
    "package.json": [
        "next", "react", "vue", "nuxt", "@sveltejs/kit", "svelte", "@angular/core",
        "express", "fastify", "@nestjs/core", "koa", "hono", "@remix-run/node", "astro",
        "prisma", "@prisma/client", "sequelize", "typeorm", "mongoose", "drizzle-orm", "knex",
        "next-auth", "@auth/core", "@clerk/nextjs", "@supabase/supabase-js", "firebase",
        "firebase-admin", "passport", "jsonwebtoken", "jose", "helmet", "cors",
        "express-rate-limit", "dompurify", "isomorphic-dompurify", "sanitize-html",
        "marked", "markdown-it", "multer", "zod", "graphql", "@trpc/server",
    ],
    "requirements.txt": ["django", "djangorestframework", "flask", "fastapi", "sqlalchemy",
                         "pyjwt", "flask-wtf", "flask-talisman", "flask-limiter", "slowapi"],
    "pyproject.toml": ["django", "djangorestframework", "flask", "fastapi", "sqlalchemy",
                       "pyjwt", "flask-wtf", "flask-talisman", "flask-limiter", "slowapi"],
    "Gemfile": ["rails", "devise", "pundit", "cancancan", "rack-attack", "brakeman"],
    "composer.json": ["laravel/framework", "symfony/"],
    "go.mod": ["gin-gonic/gin", "labstack/echo", "gofiber/fiber", "go-chi/chi", "gorilla/mux"],
    "pom.xml": ["spring-boot", "spring-security"],
    "build.gradle": ["spring-boot", "spring-security"],
    "build.gradle.kts": ["spring-boot", "spring-security"],
}


def redact(value: str) -> str:
    value = value.strip()
    if len(value) <= 8:
        return "[redacted]"
    return f"{value[:4]}…[redacted]…{value[-2:]}"


def iter_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS and f"{rel_dir}/{d}".lstrip("./") not in SKIP_DIRS
        ]
        for name in filenames:
            if name in SKIP_FILES or name.endswith((".min.js", ".map")):
                continue
            path = Path(dirpath) / name
            ext = path.suffix.lower()
            if ext not in SOURCE_EXT and not name.startswith(".env") and name not in {"Dockerfile", "_headers"}:
                continue
            try:
                if path.is_symlink() or path.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield path


def detect_stack(root: Path) -> list[str]:
    found: list[str] = []
    for manifest, markers in STACK_MARKERS.items():
        for path in [root / manifest, *root.glob(f"*/{manifest}"), *root.glob(f"*/*/{manifest}")]:
            if "node_modules" in path.parts or not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore").lower()
            except OSError:
                continue
            for marker in markers:
                needle = f'"{marker}"' if manifest == "package.json" else marker
                if needle in text and marker not in found:
                    found.append(marker)
    return found


def scan(root: Path, focus: set[str]) -> dict:
    compiled = [(c, rid, re.compile(rx, re.MULTILINE), note) for c, rid, rx, note in RULES
                if not focus or c in focus]
    secrets_on = not focus or "secrets" in focus
    secret_rules = [(rid, re.compile(rx)) for rid, rx in SECRET_RULES] if secrets_on else []
    route_rules = [(kind, re.compile(rx, re.MULTILINE)) for kind, rx in ROUTE_RULES]

    leads: dict[str, dict[str, dict]] = {}
    counts: dict[str, int] = {}
    secrets: list[dict] = []
    routes: list[dict] = []
    files_scanned = 0

    for path in iter_files(root):
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        files_scanned += 1
        lines = text.splitlines()
        is_test = bool(re.search(r"(^|/)(tests?|__tests__|spec|fixtures?|e2e|cypress)(/|$)|\.(test|spec)\.", rel))

        for kind, rx in FILE_ROUTE_PATTERNS:
            if rx.search(rel):
                routes.append({"kind": kind, "file": rel, "line": 1, "route": rel})

        for kind, rx in route_rules:
            for m in rx.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                routes.append({"kind": kind, "file": rel, "line": line,
                               "route": (m.groups()[-1] if m.groups() else "") or "(module)"})

        for category, rid, rx, note in compiled:
            for m in rx.finditer(text):
                key = f"{category}:{rid}"
                counts[key] = counts.get(key, 0) + 1
                bucket = leads.setdefault(category, {}).setdefault(rid, {"note": note, "hits": []})
                if len(bucket["hits"]) >= MAX_HITS_PER_RULE:
                    continue
                line = text.count("\n", 0, m.start()) + 1
                snippet = lines[line - 1].strip()[:160] if line - 1 < len(lines) else ""
                bucket["hits"].append({"file": rel, "line": line, "snippet": snippet, "test_or_fixture": is_test})

        for rid, rx in secret_rules:
            for m in rx.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                raw_line = lines[line - 1] if line - 1 < len(lines) else ""
                if rid in {"generic-assignment", "db-url-with-password"} and PLACEHOLDER_RE.search(raw_line):
                    continue
                secrets.append({
                    "type": rid, "file": rel, "line": line,
                    "value": "(name only)" if rid in {"client-prefixed-secret", "supabase-service-role"} else redact(m.group(0)),
                    "test_or_fixture": is_test,
                })

    return {
        "root": str(root),
        "files_scanned": files_scanned,
        "stack": detect_stack(root),
        "entry_points": routes[:400],
        "entry_point_count": len(routes),
        "leads": leads,
        "lead_counts": counts,
        "secrets": secrets[:200],
        "note": "Leads only. Trace each from source to sink and apply the validation gate before reporting.",
    }


SECURITY_HEADERS = [
    "strict-transport-security", "content-security-policy", "content-security-policy-report-only",
    "x-content-type-options", "x-frame-options", "referrer-policy", "permissions-policy",
    "cross-origin-opener-policy", "cross-origin-resource-policy", "access-control-allow-origin",
    "access-control-allow-credentials", "server", "x-powered-by",
]


def check_headers(url: str) -> dict:
    if not re.match(r"^https?://[^\s/$.?#].[^\s]*$", url):
        raise ValueError("--headers needs an http(s) URL")
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "appsec-header-check/1.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=15)  # noqa: S310 - user-owned URL, GET only
        status, headers, final = resp.status, resp.headers, resp.geturl()
    except urllib.error.HTTPError as exc:
        status, headers, final = exc.code, exc.headers, url
    present = {h: headers.get(h) for h in SECURITY_HEADERS if headers.get(h) is not None}
    missing = [h for h in ("strict-transport-security", "content-security-policy",
                           "x-content-type-options", "referrer-policy") if h not in present]
    frame_ok = "x-frame-options" in present or "frame-ancestors" in (present.get("content-security-policy") or "")
    if not frame_ok:
        missing.append("frame-ancestors (CSP) or x-frame-options")
    cookies = []
    for raw in headers.get_all("set-cookie") or []:
        name = raw.split("=", 1)[0].strip()
        lower = raw.lower()
        cookies.append({
            "name": name,
            "secure": "secure" in lower,
            "httponly": "httponly" in lower,
            "samesite": (re.search(r"samesite=(\w+)", lower) or [None, "unset"])[1],
        })
    return {"url": url, "final_url": final, "status": status, "present": present,
            "missing": missing, "cookies": cookies,
            "note": "Single unauthenticated GET. Confirm headers on authenticated and HTML pages too."}


def print_text(report: dict) -> None:
    print(f"# appsec leads for {report['root']}  ({report['files_scanned']} files)")
    print(f"stack: {', '.join(report['stack']) or 'unknown'}")
    print(f"\n## entry points ({report['entry_point_count']})")
    for r in report["entry_points"][:80]:
        print(f"  {r['file']}:{r['line']}  [{r['kind']}]  {r['route']}")
    if report["entry_point_count"] > 80:
        print(f"  … {report['entry_point_count'] - 80} more (use --json)")
    for category, rules in report["leads"].items():
        print(f"\n## {category}")
        for rid, data in rules.items():
            total = report["lead_counts"].get(f"{category}:{rid}", len(data["hits"]))
            print(f"  - {rid} ({total}): {data['note']}")
            for hit in data["hits"][:15]:
                tag = " [test]" if hit["test_or_fixture"] else ""
                print(f"      {hit['file']}:{hit['line']}{tag}  {hit['snippet']}")
    if report["secrets"]:
        print("\n## secrets (redacted)")
        for s in report["secrets"]:
            tag = " [test]" if s["test_or_fixture"] else ""
            print(f"  {s['file']}:{s['line']}{tag}  {s['type']}  {s['value']}")
    print(f"\n{report['note']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", nargs="?", help="project root to scan")
    parser.add_argument("--json", action="store_true", help="print JSON")
    parser.add_argument("--focus", default="", help="comma-separated categories "
                        "(auth,authz,injection,xss,csrf,ssrf,secrets,headers,cors,upload,ratelimit,logging)")
    parser.add_argument("--headers", metavar="URL", help="passive header check of a URL the user owns")
    args = parser.parse_args()

    if not args.root and not args.headers:
        parser.print_usage(sys.stderr)
        return 1

    out: dict = {}
    if args.headers:
        try:
            out["headers"] = check_headers(args.headers)
        except (ValueError, urllib.error.URLError, OSError) as exc:
            print(f"header check failed: {exc}", file=sys.stderr)
            return 2
    if args.root:
        root = Path(args.root).resolve()
        if not root.is_dir():
            print(f"not a directory: {root}", file=sys.stderr)
            return 1
        focus = {f.strip() for f in args.focus.split(",") if f.strip() and f.strip() != "all"}
        out["scan"] = scan(root, focus)

    if args.json:
        print(json.dumps(out, indent=2))
    else:
        if "headers" in out:
            h = out["headers"]
            print(f"# headers for {h['final_url']} (HTTP {h['status']})")
            for k, v in h["present"].items():
                print(f"  {k}: {v}")
            print(f"  missing: {', '.join(h['missing']) or 'none'}")
            for c in h["cookies"]:
                print(f"  cookie {c['name']}: secure={c['secure']} httponly={c['httponly']} samesite={c['samesite']}")
            print()
        if "scan" in out:
            print_text(out["scan"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
