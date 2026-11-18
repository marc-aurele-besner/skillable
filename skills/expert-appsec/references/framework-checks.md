# Framework-specific checks

Load the section for the stack found in SKILL.md step 1 **before** reporting a control as missing. Each section lists what the framework does by default (so you do not report it), the escape hatches that disable that default (where real bugs live), and the idiomatic fix to recommend. Defaults change between major versions — confirm the installed version from the lockfile.

---

## Next.js / React (App Router and Pages Router)

**Safe by default:** JSX escapes interpolated text; Server Actions check that `Origin` matches `Host` (CSRF) since 14; `next/image` restricts remote hosts via `images.remotePatterns`.

**Escape hatches and footguns:**
- `dangerouslySetInnerHTML` with user or CMS data; `href`/`src` from user data (`javascript:` URLs).
- **Server Actions are public POST endpoints.** Every `"use server"` function needs its own authentication and authorization check; a check in the page or layout does not protect it. Arguments are attacker-controlled — validate them (zod).
- **Route handlers** (`app/**/route.ts`) and `pages/api/*` need explicit auth; `middleware.ts` `matcher` often excludes `/api`, `_next`, or static paths — confirm the matcher actually covers protected routes. Middleware-only auth is fragile; prefer checking in the handler or a data-access layer.
- Data leaking into client components: props passed from a server component to a `"use client"` component are serialized to the browser — passing a whole user record leaks hashes and tokens. Use `server-only` imports and the taint APIs (`experimental_taintObjectReference`) where available.
- `NEXT_PUBLIC_*` and `next.config.js` `env` are inlined into the client bundle.
- `productionBrowserSourceMaps: true` exposes source.
- `images.remotePatterns` with `hostname: '**'` turns the image optimizer into an open proxy (SSRF-adjacent, cost abuse).
- `redirect(searchParams.next)` → open redirect.
- Security headers go in `next.config.js` `headers()` or middleware; nonce-based CSP via middleware.

**Idiomatic fixes:** a data-access layer that takes the session and scopes queries; `zod` parsing at the top of every action and route handler; `headers()` in `next.config.js` for HSTS/nosniff/frame-ancestors; nonce CSP in middleware.

## Express / Fastify / NestJS (Node.js)

**Safe by default:** very little in Express — no CSRF, no headers, no body limits beyond `100kb` for `express.json()`. Fastify validates against JSON Schema when schemas are declared. NestJS `ValidationPipe` only strips unknown fields with `whitelist: true`.

**Footguns:**
- No `helmet()` → missing headers; check edge config before reporting.
- `cors({ origin: true, credentials: true })` reflects any origin — High.
- `app.set('trust proxy', true)` trusts every hop's `X-Forwarded-For`; rate limits keyed on `req.ip` are then spoofable. Set it to the real hop count or proxy list.
- `express-rate-limit` default memory store on multi-instance deploys.
- `express.static` rooted at the project directory.
- Session: `express-session` with `MemoryStore` in production, `cookie.secure` false, a hardcoded `secret`.
- NoSQL operator injection with Mongoose when query values come from `req.body` without casting; `qs` nested parsing (`?user[$ne]=x`).
- `child_process.exec` with template strings.
- Error handler leaking `err.stack` when `NODE_ENV` is not `production`.
- NestJS: guards applied per controller — a new controller without `@UseGuards` is open unless a global guard is registered (`APP_GUARD`). `ValidationPipe` without `whitelist`/`forbidNonWhitelisted` allows mass assignment into entities.

**Idiomatic fixes:** `helmet()`; explicit CORS allow-list; `express-rate-limit` with a Redis store on auth routes; `zod`/`class-validator` DTOs; `execFile` with arrays; a global auth guard with explicit `@Public()` opt-outs.

## Django / Django REST Framework

**Safe by default:** template autoescaping; CSRF middleware; ORM parameterization; `SecurityMiddleware`; clickjacking middleware (`X-Frame-Options: DENY`); password hashers (PBKDF2/argon2).

**Escape hatches:** `|safe`, `mark_safe`, `{% autoescape off %}`, `format_html` misuse; `.raw()`, `.extra()`, `RawSQL`, `cursor.execute(f"...")`; `@csrf_exempt`; `DEBUG = True` in production; `ALLOWED_HOSTS = ['*']` (host-header poisoning of reset links); `SECRET_KEY` committed.
- **Settings to verify for production:** `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_PROXY_SSL_HEADER` (only behind a proxy that sets it).
- **DRF:** `DEFAULT_PERMISSION_CLASSES` defaults to `AllowAny` — check the setting and every viewset; `get_queryset` must scope to the user (object-level IDOR is the most common DRF bug); `ModelSerializer` with `fields = '__all__'` exposes and accepts every column (mass assignment, data exposure); `has_object_permission` is not called for list views.
- `pickle`-based session serializer or cache with untrusted data.

**Idiomatic fixes:** `get_queryset` filtered by `request.user`; explicit serializer `fields` and `read_only_fields`; `IsAuthenticated` as the default permission; `python manage.py check --deploy`.

## Flask / FastAPI (Python)

**Flask safe by default:** Jinja2 autoescape for `.html` templates. **Not provided:** CSRF (needs Flask-WTF), headers (Flask-Talisman), rate limits (Flask-Limiter). Footguns: `render_template_string` with user input (SSTI → RCE, Critical); `app.run(debug=True)` exposes the Werkzeug debugger (RCE); `send_file(request.args['path'])` (use `send_from_directory` / `safe_join`); session cookie signed with a weak `SECRET_KEY` (sessions are client-side and readable — never put secrets in them).

**FastAPI safe by default:** pydantic validation of declared bodies and params. Footguns: auth implemented as a dependency that a new router forgets (prefer router-level `dependencies=[Depends(...)]`); returning ORM objects without a `response_model` leaks fields; `CORSMiddleware(allow_origins=["*"], allow_credentials=True)` (Starlette reflects the origin in this case — High); SQLAlchemy `text(f"...")`.

## Ruby on Rails

**Safe by default:** ERB escaping; `protect_from_forgery` (CSRF) in `ApplicationController`; ActiveRecord parameterization with hash/array conditions; strong parameters; default security headers; `config.force_ssl` in production templates.

**Escape hatches:** `raw`, `html_safe`, `<%==`; `where("name = '#{params[:name]}'")`, `order(params[:sort])`, `pluck`/`select` with interpolation; `skip_forgery_protection` / `protect_from_forgery with: :null_session` on cookie-authenticated controllers; `params.permit!`; `send_file params[:path]`; `redirect_to params[:url]` (Rails 7 raises on external hosts unless `allow_other_host: true`); `YAML.load` (unsafe before Psych 4), `Marshal.load`; `constantize` on user input.
- Authorization: Pundit `authorize`/`policy_scope` or CanCanCan — check `after_action :verify_authorized` exists, otherwise a new action skips it silently.
- `config.hosts` empty in production; `secret_key_base` in the repo; `config.filter_parameters` missing tokens.

**Idiomatic fixes:** `current_user.projects.find(params[:id])` (scoped finder); Pundit with `verify_authorized`; Brakeman for a quick candidate list.

## Laravel (PHP)

**Safe by default:** Blade `{{ }}` escaping; `VerifyCsrfToken` middleware for web routes; Eloquent bindings; `$fillable`/`$guarded` mass-assignment protection.

**Escape hatches:** `{!! !!}`; `DB::raw`, `whereRaw`, `orderByRaw` with interpolation; `$guarded = []`; `VerifyCsrfToken::$except`; `APP_DEBUG=true` in production (Ignition leaks env); `APP_KEY` committed; `unserialize` on user data; `Storage::disk('public')` serving user HTML/SVG.
- Authorization: Policies and `$this->authorize()` / `can` middleware — check every controller method, including API routes in `routes/api.php` (no CSRF, so auth must be token-based).

## Spring Boot / Spring Security (Java, Kotlin)

**Safe by default:** Spring Security enables CSRF, security headers, and session fixation protection when on the classpath; Thymeleaf escapes `th:text`; JPA parameter binding.

**Escape hatches:** `http.csrf().disable()` on a cookie-session app; `th:utext`; JPQL/native queries built with `+`; `permitAll()` on overly broad matchers (`/api/**`), and matcher order mistakes (first match wins); `@PreAuthorize` missing on new methods without `@EnableMethodSecurity`; Actuator endpoints exposed (`management.endpoints.web.exposure.include=*` → `/actuator/env`, `/heapdump` leak secrets, Critical); Jackson default typing (`enableDefaultTyping`, `@JsonTypeInfo(use = Id.CLASS)`) → deserialization RCE; XML parsers without XXE hardening; SpEL evaluation of user input.

## Go (net/http, Gin, Echo, Fiber)

**Safe by default:** `html/template` contextual escaping; `database/sql` placeholders.

**Footguns:** `text/template` for HTML; `template.HTML(userValue)`; `fmt.Sprintf` into SQL; `exec.Command("sh", "-c", userString)`; `http.ServeFile`/`filepath.Join` with user paths (use `filepath.Clean` + prefix check, or `os.Root` / `http.FS` with `fs.Sub`); default `http.Client` follows redirects (SSRF re-validation needed); no request body limit (`http.MaxBytesReader`); servers without `ReadHeaderTimeout` (Slowloris, Low–Medium); `InsecureSkipVerify: true`.

## Vue / Nuxt, Angular, SvelteKit

- **Vue/Nuxt:** mustache escapes; `v-html` does not. Nuxt `runtimeConfig.public` and `NUXT_PUBLIC_*` ship to the client. Server routes in `server/api` need explicit auth.
- **Angular:** sanitizes `[innerHTML]` by default; `bypassSecurityTrustHtml/Url/ResourceUrl` disables it — trace what flows in. Template injection if user input reaches the compiler (JIT).
- **SvelteKit:** `{@html}` is raw; form actions have a built-in origin check (`csrf.checkOrigin`, on by default — check it was not disabled); `$env/static/public` and `PUBLIC_*` ship to the client; `+server.ts` endpoints need explicit auth; `hooks.server.ts` `handle` is the place for auth and headers.

## Backend-as-a-service (Supabase, Firebase, Appwrite)

- The client key is public by design; the **database policies are the authorization layer**.
- **Supabase:** every table in an exposed schema needs RLS enabled with policies using `auth.uid()`; `service_role` key must never reach the client; `security definer` functions bypass RLS — check them; storage buckets marked public; policies `using (true)` on write.
- **Firebase:** Firestore/RTDB/Storage rules — `allow read, write: if true` or `if request.auth != null` (any signed-in user reads everything) is the classic IDOR; check `request.auth.uid == resource.data.ownerId` patterns; Admin SDK credentials in client code.

## Platforms, proxies, and edge config

- **Vercel:** headers in `vercel.json` or `next.config.js`; preview deployments are public by default (deployment protection setting) and may use production secrets — Medium if they expose real data.
- **Netlify / Cloudflare Pages:** `_headers` and `netlify.toml` `[[headers]]`; functions under `netlify/functions` and `functions/` are public endpoints.
- **Cloudflare Workers:** secrets via `wrangler secret`, not `[vars]` in `wrangler.toml` (committed, plain text).
- **nginx:** `add_header` in a `location` block drops headers inherited from `server` unless repeated; `alias` with a missing trailing slash → path traversal (`location /static { alias /var/www/static/; }`); `merge_slashes off` surprises; `proxy_pass` with user-controlled host.
- **Docker:** secrets in `ENV`/`ARG` persist in image layers; `.dockerignore` missing `.env` and `.git`.
- **GitHub Actions (secrets exposure only):** `pull_request_target` checking out PR head code with secrets available; secrets echoed in logs. Deeper workflow hardening → `optimize-github-actions`.
