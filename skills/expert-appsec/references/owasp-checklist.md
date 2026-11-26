# OWASP review checklist

Deep checklist behind step 3 of the skill. Each category lists the sources and sinks to trace, what makes a control effective, the classic ways a control fails, and what not to report. Map each finding to its OWASP Top 10 (2021) category and, where useful, the OWASP ASVS 4.0 chapter. OWASP Top 10 2025 and ASVS 5.0 renumber several of these (for example, SSRF folds into A01 and injection moves to A05 in the 2025 list; ASVS 5.0 restructures the chapters), so if the team tracks those editions, say which edition each id comes from instead of mixing them. Every candidate still goes through the validation gate in SKILL.md step 4.

| Category | OWASP Top 10 | ASVS |
|----------|--------------|------|
| Authentication and sessions | A07 Identification and Authentication Failures | V2, V3 |
| Authorization and IDOR | A01 Broken Access Control | V4 |
| Injection | A03 Injection (A08 for deserialization) | V5 |
| XSS and CSP | A03 Injection | V5.3, V14.4 |
| CSRF | A01 Broken Access Control | V4.2.2, V3.4 |
| SSRF | A10 Server-Side Request Forgery | V12.6 |
| Secrets | A02 Cryptographic Failures / A05 Security Misconfiguration | V6.4, V14.3 |
| Security headers | A05 Security Misconfiguration | V14.4 |
| CORS | A05 Security Misconfiguration | V14.5.3 |
| File upload | A04 Insecure Design / A05 | V12 |
| Rate limiting | A04 Insecure Design / A07 | V2.2, V11 |
| Logging and data exposure | A09 Security Logging and Monitoring Failures / A01 | V7, V8 |

---

## 1. Authentication and sessions

**Trace:** login, signup, password reset, email change, MFA enrollment and verification, OAuth/OIDC callback, magic links, "remember me", API key issuance, logout.

| Check | Effective control | How it fails |
|-------|-------------------|--------------|
| Password storage | argon2id, scrypt, bcrypt (cost ≥ 10), or PBKDF2 with high iterations, via a maintained library | MD5/SHA-1/SHA-256 unsalted or single-round; custom hashing; plaintext in a column or log |
| Comparison | Library verify function; constant-time compare for tokens (`crypto.timingSafeEqual`, `hmac.compare_digest`) | `==` on reset tokens or API keys (timing is minor; the bigger bug is usually the token itself) |
| Reset tokens | ≥ 128 bits from a CSPRNG, single-use, short expiry (≤ 1 h), stored hashed, invalidated on use and on password change | Sequential or time-based tokens; token in a URL logged by analytics; reset link built from the `Host` header (host-header poisoning); token not tied to the user |
| Session cookie | `HttpOnly`, `Secure`, `SameSite=Lax` or `Strict`, `__Host-` prefix where possible, server-side expiry | Session id readable by JS; no `Secure` on an HTTPS app; no idle/absolute timeout |
| Session lifecycle | Regenerate the session id on login and privilege change; destroy server-side on logout; invalidate other sessions on password change | Session fixation (id kept across login); logout only clears the cookie client-side while the token stays valid |
| JWT | `verify` with a pinned algorithm list, check `exp`, `nbf`, `aud`, `iss`; short-lived access tokens; refresh rotation with reuse detection | `decode` without verify; `alg: none`; HS256 with the RS public key; secret is a default (`secret`, `changeme`); no revocation path for a stolen token |
| OAuth / OIDC | `state` (CSRF) and PKCE; exact `redirect_uri` match; `nonce` for OIDC; verify the ID token; link accounts only on a verified email | Missing `state`; open redirect in `redirect_uri` or post-login `next`/`returnTo`; account takeover by linking on an unverified email from the provider |
| MFA | Enforced server-side on every login path; OTP rate-limited and single-use; recovery codes hashed | MFA checked only in the UI; a second login endpoint (API, mobile) skips it; OTP brute-forceable |
| Enumeration | Same response and similar timing for "unknown user" and "wrong password"; reset says "if the account exists…" | Distinct messages or status codes, usually **Low**, unless combined with no rate limit |
| Open redirect | Allow-list of relative paths; reject `//evil.com`, `/\evil.com`, `https:` schemes | `res.redirect(req.query.next)`, Medium alone, High when it leaks OAuth codes or tokens |

**What not to report:** password complexity rules alone, missing MFA on an app that never offered it (Info at most), enumeration on a public-profile product where usernames are public anyway.

## 2. Authorization and IDOR

**Trace:** every handler that reads, updates, or deletes an object by an id from the request, path params, query, body, GraphQL args, server action args, WebSocket messages.

| Check | Effective control | How it fails |
|-------|-------------------|--------------|
| Object-level (BOLA/IDOR) | Query scoped to the caller: `where: { id, ownerId: user.id }` or tenant id; a shared policy (`authorize(user, 'update', doc)`); Postgres RLS | `findById(req.params.id)` then return; ownership checked on read but not on update/delete; check uses a client-sent `userId` |
| Function-level | Role check enforced server-side on every admin route and action, ideally by router-level middleware | Admin pages hidden in the UI but the API is open; `isAdmin` read from a client-controlled field or unsigned cookie |
| Tenant isolation | Tenant id derived from the session, applied by a default query scope or RLS | Tenant id from a header or subdomain without verifying membership; a background job or export that drops the scope |
| Mass assignment | Explicit allow-list of writable fields (DTO, zod schema, strong params, `fillable`) | `update(req.body)` lets a user set `role`, `ownerId`, `isVerified`, `balance`, `tenantId` |
| Indirect references | Signed or unguessable ids do not replace checks | UUIDs treated as authorization ("nobody can guess it") while ids leak through lists, URLs, or emails |
| GraphQL | Authorization per resolver or field, including nested resolvers; depth/complexity limits | `user { orders { … } }` traverses into another user's data because only the top-level resolver checks |
| File and export access | Signed URLs with short expiry, scoped per object; downloads go through an authorization check | Public bucket with predictable keys; `/download?path=` reads any file |

**Failure scenario shape:** "signed in as user A (role `member`), `PATCH /api/projects/<B's id>` with `{ "name": "x" }` succeeds."

**What not to report:** a missing check on a resource that is public by design (verify in docs or UI), or admin-only actions being available to admins.

## 3. Injection

**Trace:** request data into any interpreter: SQL, NoSQL query objects, shell, template engines, file paths, XPath/LDAP, headers, deserializers, `eval`.

| Sink | Effective control | How it fails |
|------|-------------------|--------------|
| SQL | Parameterized queries / ORM bindings; identifiers (column, sort, table) from an allow-list | String concatenation or interpolation into raw SQL; `ORDER BY ${sort}`; `LIKE '%${q}%'`; ORM raw escape hatches (see SKILL.md gotchas) |
| NoSQL (MongoDB) | Cast inputs to expected primitive types; schema validation; `sanitizeFilter` / strict query | `find({ user: req.body.user, pass: req.body.pass })` where body is `{ "$ne": null }` → operator injection; `$where` with user strings |
| OS command | `execFile`/`spawn` with an argument array and no shell; `subprocess.run([...], shell=False)`; allow-list arguments; `--` before user args | `exec(\`convert ${file}\`)`, `shell=True`, `os.system`, backticks in Ruby, `Runtime.exec(String)`; argument injection (`--output=/etc/...`) even without a shell |
| Template (SSTI) | Never compile user input as a template; render user data as variables only | `render_template_string(user_input)`, `new Function`, Handlebars/EJS/Pug/Twig/Freemarker compiling user-provided templates |
| Path traversal | Resolve, then confirm the result is inside the base dir (`path.resolve` + prefix check, `safe_join`, `Path.resolve().is_relative_to()`); use ids, not names | `path.join(base, req.query.file)` with `../`; URL-decoding after the check; zip-slip on archive extraction; Windows `\` and drive letters |
| Header / CRLF | Framework header APIs that reject newlines | Raw header writes with user data; `Content-Disposition` filename not encoded |
| Deserialization | JSON only; schema-validated | `pickle.loads`, `yaml.load` (not `safe_load`), Java `ObjectInputStream`, PHP `unserialize`, `Marshal.load`, `node-serialize` on user data |
| Prototype pollution | Reject `__proto__`, `constructor`, `prototype` keys; `Object.create(null)`; maintained merge libs | Deep-merge or set-by-path of request JSON into objects; query parsers creating nested objects |
| `eval` family | None needed: remove it | `eval`, `Function()`, `vm.runInContext` (not a sandbox), `setTimeout(string)`, Python `eval`/`exec` on request data |
| Regex (ReDoS) | Linear-time engines (RE2) or bounded input length | User-supplied regex; catastrophic patterns like `(a+)+$` on user input, Medium (availability) |

**What not to report:** raw SQL with only constant strings or allow-listed identifiers; `exec` with fully constant arguments; template compilation of developer-owned files.

## 4. XSS and CSP

**Trace:** user-controlled data (including stored data) into HTML, attributes, URLs, inline scripts, and DOM APIs.

| Sink | Effective control | How it fails |
|------|-------------------|--------------|
| Raw HTML | Avoid; if needed, sanitize with DOMPurify (client) or a maintained server sanitizer (bleach successor `nh3`, `sanitize-html`, `HtmlSanitizer`) with a strict allow-list | `dangerouslySetInnerHTML`, `v-html`, `[innerHTML]`, `|safe`, `html_safe`, `{!! !!}` on user data; homemade regex sanitizers |
| URL attributes | Allow-list `http:`/`https:`/`mailto:` schemes; parse with `URL` | `href={user.website}` → `javascript:alert(1)`; `src`, `formaction`, `xlink:href` |
| DOM | `textContent`, `setAttribute` on safe attributes | `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, jQuery `.html()`/`$(userString)`, `location = userValue` |
| Inline script data | Serialize with a JSON encoder that escapes `<`, `>`, `&`, U+2028/2029 (`serialize-javascript`, `json_script` in Django) | `<script>window.__DATA__ = ${JSON.stringify(data)}</script>` → `</script>` breakout |
| Markdown / rich text | Renderer with HTML disabled or sanitized output; link scheme allow-list | `marked` / `markdown-it` with `html: true` and no sanitizer; WYSIWYG HTML stored and rendered raw |
| SVG / HTML uploads | Serve from a separate origin or with `Content-Disposition: attachment` and a strict `Content-Type` | User SVG served inline from the app origin → stored XSS |
| CSP | Nonce- or hash-based `script-src` with `'strict-dynamic'`; no `'unsafe-inline'` for scripts; `object-src 'none'`; `base-uri 'none'`; `frame-ancestors` | No CSP on an app with HTML sinks; `script-src 'unsafe-inline' *`; allow-listed CDNs that host JSONP or arbitrary user content; report-only never enforced |

**Severity:** stored XSS reaching other users or admins → High; reflected XSS needing a click → Medium; DOM XSS from `location.hash` → Medium; self-XSS → do not report. A strong enforced CSP can lower a finding one level; say so.

**What not to report:** framework-escaped interpolation (`{value}` in JSX, `{{ value }}` in Vue/Jinja with autoescape), `dangerouslySetInnerHTML` on constant or developer-authored content, a missing CSP on a JSON API.

## 5. CSRF

**Trace:** every state-changing request authenticated by a cookie (session or JWT in a cookie).

| Check | Effective control | How it fails |
|-------|-------------------|--------------|
| Token | Framework CSRF protection on (Django, Rails, Laravel, Spring, `csurf` successors such as `csrf-csrf`, SvelteKit/Next.js server actions' origin check) | Protection disabled globally or exempted (`@csrf_exempt`, `skip_forgery_protection`, `VerifyCsrfToken::$except`) on sensitive routes |
| SameSite | `SameSite=Lax` or `Strict` on session cookies | `SameSite=None` without a token; reliance on Lax while a GET handler changes state |
| Method semantics | No side effects on GET/HEAD | `GET /logout`, `GET /api/delete?id=` , `GET /confirm-transfer` |
| Origin check | Verify `Origin` / `Sec-Fetch-Site` on state changes | Missing for JSON endpoints that accept `text/plain` or form encodings (simple requests bypass preflight) |
| Login CSRF | Token on the login form | Attacker logs the victim into the attacker's account (Low–Medium) |

**What not to report:** CSRF on APIs authenticated only by an `Authorization` header (browsers do not attach it cross-site), or on endpoints with no state change.

## 6. SSRF

**Trace:** any server-side request whose URL, host, or path comes from the user, link previews, webhooks, image/PDF/HTML renderers, import-from-URL, OAuth/OIDC discovery with user-supplied issuers, XML external entities, headless browsers.

| Check | Effective control | How it fails |
|-------|-------------------|--------------|
| Destination | Allow-list of hosts; resolve DNS and block private, loopback, link-local, and metadata ranges (IPv4 and IPv6) on the resolved IP; connect to the IP you checked | Hostname-only check (DNS rebinding); blocking `localhost` but not `127.1`, `0.0.0.0`, `[::1]`, `2130706433`, `169.254.169.254`, `fd00::/8` |
| Redirects | Disable automatic redirects or re-validate each hop | Allowed host 302s to `http://169.254.169.254/latest/meta-data/` |
| Schemes | `http`/`https` only | `file://`, `gopher://`, `dict://` via curl-backed clients |
| Response handling | Do not return raw responses to the user; cap size and time | Full internal response echoed back (non-blind SSRF → High/Critical) |
| Cloud metadata | IMDSv2 required (AWS), metadata concealment (GCP), egress firewall | IMDSv1 reachable → credential theft (Critical) |
| XXE | Disable DTDs/external entities in XML parsers (`defusedxml`, `XMLInputFactory` hardening) | Default `libxml`/Java parsers on user XML, SVG, DOCX |

**What not to report:** fetches to fixed, developer-configured URLs; URLs the user supplies that are fetched only by the user's own browser.

## 7. Secrets

**Look in:** source, config, `.env*` committed, Docker and CI files, test fixtures, mobile and front-end bundles, source maps, notebook outputs, git history (`git log -p -S '<prefix>'` for a suspected key prefix).

| Check | Effective control | How it fails |
|-------|-------------------|--------------|
| Repo | Secrets from env or a secret manager; `.env` in `.gitignore`; `.env.example` with placeholders | Live keys in code or history; private keys (`-----BEGIN … PRIVATE KEY-----`); DB URLs with passwords |
| Client bundle | Only publishable/anon keys under client prefixes | Server secret under `NEXT_PUBLIC_`/`VITE_`; server module imported into a client component; secret in `next.config.js` `env` (inlined) |
| Source maps | Not deployed publicly, or uploaded privately to the error tracker | `productionBrowserSourceMaps: true`, `build.sourcemap: true` exposing server-side comments and internal endpoints |
| Static serving | Static root excludes config | `express.static('.')` or a web root that serves `.env`, `.git/` |
| Defaults | No fallback secrets in code | `process.env.JWT_SECRET || 'dev-secret'`, Critical if production can fall through |
| Crypto | Keys long and random; no hardcoded IVs; AES-GCM or libsodium; no ECB | Hardcoded encryption key; `Math.random` for tokens |

**Severity:** a live production secret with write access → Critical; a test or revoked key → Low/Info (confirm with the user, never test it yourself). Always redact.

## 8. Security headers

Check code (Helmet, `next.config.js` `headers()`, Django `SECURE_*` settings, Rails `config.force_ssl`, Spring Security headers) **and** platform/edge config (`vercel.json`, `netlify.toml`, `_headers`, nginx, Cloudflare). Verify live only on a URL the user owns.

| Header | Recommended | Notes |
|--------|-------------|-------|
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` (add `preload` only deliberately) | Missing HSTS on an HTTPS app with session cookies → Low/Medium |
| `Content-Security-Policy` | See XSS section | Its absence matters in proportion to the app's HTML sinks |
| `X-Content-Type-Options` | `nosniff` | Matters most where user uploads are served |
| `frame-ancestors` / `X-Frame-Options` | `frame-ancestors 'none'` or `'self'` / `DENY` | Clickjacking on sensitive one-click actions → Medium; otherwise Low |
| `Referrer-Policy` | `strict-origin-when-cross-origin` or stricter | Matters when URLs carry tokens |
| `Permissions-Policy` | Disable unused powerful features | Info unless the app is embedded |
| Cookies | `Secure; HttpOnly; SameSite=Lax`, `__Host-` prefix | Session cookie flags are an auth finding, not a header nit |

**What not to report:** `X-XSS-Protection` (deprecated: recommend removing it or `0`), `Server`/`X-Powered-By` version disclosure as a standalone finding (Info at most), missing headers on a pure JSON API except HSTS.

## 9. CORS

| Check | Effective control | How it fails |
|-------|-------------------|--------------|
| Origin allow-list | Exact-match list of trusted origins | Reflecting `req.headers.origin` with `credentials: true` → any site reads authenticated responses (High) |
| Matching | Parse the origin and compare scheme + host + port exactly | `origin.endsWith('example.com')` matches `evilexample.com`; unescaped dots in regex; `startsWith('https://example.com')` matches `https://example.com.evil.io` |
| `null` origin | Never allow-listed | Sandboxed iframes and `file://` send `Origin: null` |
| Wildcard | `*` only for truly public, unauthenticated, read-only resources | `*` on an API that authenticates by IP or internal network position |
| Preflight | Minimal allowed methods and headers; reasonable `max-age` | `Access-Control-Allow-Headers: *` with credentials (ignored by browsers, but signals a reflected config) |

**What not to report:** `Access-Control-Allow-Origin: *` without credentials on public data.

## 10. File upload

| Check | Effective control | How it fails |
|-------|-------------------|--------------|
| Type | Validate content (magic bytes) against an allow-list; set `Content-Type` from your allow-list, not the client | Trusting the extension or client MIME; allowing `.html`, `.svg`, `.xml`, `.php`, `.jsp` |
| Size and count | Limits at the parser (`multer` limits, `client_max_body_size`, `DATA_UPLOAD_MAX_MEMORY_SIZE`) | Unbounded uploads → disk/memory exhaustion |
| Name and path | Generate storage keys server-side; never use the client filename in a path | Path traversal via `../../`; overwriting other users' files |
| Serving | Separate domain (user-content origin) or object storage with `Content-Disposition: attachment` and `nosniff` | Uploaded HTML/SVG served from the app origin → stored XSS with the app's cookies |
| Processing | Patched image libraries; limits on pixel count (decompression bombs); safe archive extraction | ImageMagick/Ghostscript on untrusted files without policy; zip-slip; XXE via DOCX/SVG |
| Direct-to-storage | Pre-signed URLs scoped to one key, content type, and size, short expiry | Pre-signed POST policy without `content-length-range` or key prefix |
| Malware | Scan if files are shared with other users | Info unless the product distributes files |

## 11. Rate limiting and abuse

| Check | Effective control | How it fails |
|-------|-------------------|--------------|
| Credential endpoints | Limits per account and per IP on login, reset, OTP, MFA, signup; lockout or progressive delay | No limit on a 6-digit OTP → brute force in minutes (High) |
| Key choice | Key on account id and trusted client IP | Keyed on `X-Forwarded-For` without `trust proxy` configuration → rotate the header to bypass |
| Storage | Shared store (Redis) across instances | In-memory limiter on a multi-instance or serverless deploy, effectively no limit |
| Cost amplification | Limits on expensive endpoints (search, export, AI calls, email/SMS sends) | Unauthenticated endpoint that sends SMS → toll fraud; LLM endpoint without per-user quotas |
| Enumeration | Uniform responses + limits | Unlimited `/api/users/check-email` |
| Pagination | Server-enforced max page size | `?limit=1000000` |

**What not to report:** missing limits on cheap, idempotent, public read endpoints already behind a CDN, unless there is a concrete cost or enumeration impact.

## 12. Logging and data exposure

| Check | Effective control | How it fails |
|-------|-------------------|--------------|
| Secrets in logs | Redaction in the logger (pino `redact`, structlog processors, Rails `filter_parameters`, Django `sensitive_variables`) | Logging full `req.body` on login; logging `Authorization` headers; tokens in URLs captured by access logs |
| PII | Minimize; mask; retention limits | Emails, addresses, health or payment data in debug logs or analytics events |
| Error trackers | `beforeSend` scrubbing in Sentry and similar; `sendDefaultPii: false` | Request bodies and cookies shipped to a third party |
| Errors to clients | Generic messages in production; `DEBUG=False`; no stack traces | Django `DEBUG=True`, Express default error handler in prod, GraphQL errors exposing SQL |
| Over-returning | Explicit response serializers/DTOs | Returning the whole user row (`passwordHash`, `resetToken`, `mfaSecret`) to the client |
| Security events | Log auth failures, permission denials, and admin actions without the secrets | No audit trail for admin actions, Info unless compliance requires it |
| GraphQL | Introspection disabled in production if the schema is private; field-level auth | Introspection on is Info, not a vulnerability by itself |

---

## Cross-cutting "do not report" list

- Anything already prevented by a framework default confirmed in `framework-checks.md`.
- Findings that require the attacker to already be an admin, unless they escalate further (e.g. admin → RCE on a multi-tenant host).
- Self-XSS, clickjacking on pages with no state-changing action, and missing headers on non-HTML responses.
- Dependency CVEs: hand them to `audit-vulnerabilities`.
- Generic advice ("consider a WAF", "add pentesting") with no tie to the code.
