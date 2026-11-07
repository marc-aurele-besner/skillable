# Detection reference

Per-language tooling, config, dynamic-reference pitfalls, and the standard false-positive list. Read the section for the target stack before running anything.

## Contents

- [Choosing a detector](#choosing-a-detector)
- [JavaScript and TypeScript](#javascript-and-typescript)
- [Python](#python)
- [Go](#go)
- [Rust](#rust)
- [Ruby](#ruby)
- [Java and Kotlin](#java-and-kotlin)
- [C, C++, and everything else](#c-c-and-everything-else)
- [Orphan file detection](#orphan-file-detection)
- [Dead feature flags](#dead-feature-flags)
- [Unreachable routes](#unreachable-routes)
- [Stale assets](#stale-assets)
- [Unused i18n keys](#unused-i18n-keys)
- [Commented-out code](#commented-out-code)
- [Dynamic-reference pitfalls](#dynamic-reference-pitfalls)
- [Standard false positives](#standard-false-positives)

## Choosing a detector

Prefer the project's existing tooling. Only add a new dev dependency when the project has none and the value is clear — and commit its config so the check is reproducible.

| Project already has | Use |
|---------------------|-----|
| ESLint | `no-unused-vars` for locals; add `no-unused-imports` if the plugin is present |
| TypeScript | `tsc --noUnusedLocals --noUnusedParameters` (check `tsconfig.json` first) |
| A bundler | Its own stats/tree view: `webpack-bundle-analyzer`, `vite --debug`, `rollup-plugin-visualizer` |
| A test suite with coverage | Coverage over untested files, plus the import graph |

Run every detector from the repository root so relative paths, workspace globs, and `tsconfig` `include` patterns resolve.

## JavaScript and TypeScript

**knip** — the most complete option. It reports unused files, exports, dependencies, and types, and it reads the project's own entry points.

```bash
npx knip                       # report
npx knip --reporter json       # machine-readable
npx knip --include files,exports,types
```

Config lives in `knip.json`, `knip.ts`, or the `knip` key of `package.json`. Tell it the real entry points, or it will call your app entry point an orphan:

```json
{
  "entry": ["src/index.ts", "src/cli.ts", "scripts/*.ts"],
  "project": ["src/**/*.{ts,tsx}"],
  "ignore": ["src/generated/**", "src/**/*.d.ts"]
}
```

**ts-prune** — exports only. It reports every exported name nothing imports.

```bash
npx ts-prune
npx ts-prune -i 'Foo' 'Bar'   # ignore names
```

**ESLint** — locals and imports only; it does not follow cross-file exports.

```bash
npx eslint . --rule '{"no-unused-vars":"error"}'
npx eslint . --rule '{"no-unused-imports":"error"}' --plugin unused-imports
```

TypeScript compiler flags are the cheapest first pass:

```bash
npx tsc --noEmit --noUnusedLocals --noUnusedParameters
```

TypeScript's `noUnusedLocals` does **not** flag exported symbols — a file-level `export` silences the warning. That is why `knip` or `ts-prune` is needed for the export layer.

**Monorepos:** run knip per workspace package (`knip --workspace packages/*`) or configure `workspaces`; a single root run misses package-level exports.

## Python

```bash
ruff check --select F401,F811,F841 .          # unused imports, redefinitions, unused variables
vulture . --min-confidence 80                  # unused functions, classes, methods, unreachable code
vulture . --min-confidence 60                  # noisier; review every hit by hand
python -m pyflakes .                           # if ruff is unavailable
```

`vulture` confidence levels: 60 = unused import, 80 = unused function/class/variable, 90 = unused attribute, 100 = unreachable code. Run it from the repo root so package context is available, and whitelist deliberate public API:

```bash
vulture . --exclude 'src/api/__init__.py' --exclude 'tests/*'
```

`# noqa: F401` marks a deliberate re-export; do not remove those. A module with `__all__` is a public surface — treat its names as exported API, not dead code.

`pytest --collect-only` and `python -m compileall` confirm the tree still imports after each removal.

## Go

```bash
go vet ./...
staticcheck -unused ./...
go mod tidy -diff          # unused module requirements; Go 1.23+
gopls check ./...           # unused variables, unused imports
```

`staticcheck -unused` finds unused functions, types, fields, and constants, and understands Go's package model. It respects `//lint:ignore` directives — those are deliberate.

Anything with a lowercase first letter is unexported and invisible outside its package; anything exported is part of the package's API even if the package is internal. Check `internal/` boundaries before treating an exported symbol as removable.

## Rust

```bash
cargo clippy --all-targets -- -W dead_code
cargo +nightly udeps          # unused dependencies (needs nightly)
cargo machete                 # unused dependencies, stable
```

`dead_code` is a per-crate lint: a `pub` item in a library crate is not reported even if nobody uses it, because it is public API. `cargo udeps` reports unused dependencies; `cargo machete` is the stable alternative and handles dev-dependencies and build-dependencies correctly.

## Ruby

```bash
bundle exec rubocop --only Lint/UselessAssignment,Lint/Void,Lint/UnusedMethodArgument
bundle exec vulture .
```

Rails: `bin/rails routes` lists every route — a controller action not in the route file is unreachable unless it is called directly. `config/routes.rb`, `config/initializers/`, and `config/application.rb` all reference classes by string; grep the class name as a string before deleting it.

## Java and Kotlin

```bash
mvn dependency:analyze        # unused and undeclared dependencies
./gradlew dependencies
```

Dead code in JVM languages needs an IDE analyzer (IntelliJ "Analyze Code" -> "Unused declarations") or a coverage tool (JaCoCo / Istanbul for JS) that reports classes with zero coverage. Both are noisy: a class referenced only by reflection, by a serializer, by an ORM entity, or by a `ServiceLoader` will look unused.

Maven Shade / Spring Boot fat jars list every class in the artifact; compare that list against the source tree to find classes that are packaged but never loaded.

## C, C++, and everything else

```bash
clang-tidy --checks='-Wunused-*' -p build compile_commands.json
cppcheck --enable=unusedFunction,unusedVariable --inline-suppr .
```

Compile-database aware tools (`clang-tidy -p build`) give the best results. `gcc -Wunused` misses unused static functions in other translation units; `nm` on the final binary shows what actually made it in:

```bash
nm -C --defined-only ./target/app | head -100
```

C++ static initializers and templates defeat most static analysis. Registering a type with a factory or a global registry makes it used even without a direct call site — grep for the type name as a string.

## Orphan file detection

A file is an orphan when no other file imports it and it is not an entry point. Detection:

- knip's "unused files" report (best for JS/TS).
- `depcruise` with a rule that flags files with no inbound dependencies.
- Language-specific: `python -m py_compile` plus an AST import scan; `go list -deps` for Go; `cargo` module graph for Rust.
- The bundled heuristic in `scripts/find_dead_code.py` covers the exported-symbol layer only.

Never treat a file as an orphan until you have ruled out: file-based routing, test and fixture directories, migrations and seeds, config and schema files, `__init__.py` re-exports, and codegen templates.

## Dead feature flags

A flag is dead when it is a constant at its definition site, or when no code ever writes a different value.

```bash
rg -n 'feature_[a-z_]+' src/            # find every reference to the flag name
rg -n 'FEATURE_[A-Z_]+\s*=\s*(True|False)' .   # constant definitions
```

Check for a remote-config writer (LaunchDarkly, Unleash, Firebase Remote Config, a config service) before removing anything — a flag with no local writer may still be set remotely, which makes the local branch dead but the flag alive.

Also: a flag whose value never changes at runtime is a constant, and the branches it guards are dead code. Remove the flag, the branches, and the code together.

## Unreachable routes

Build the route table and compare it with the links in the app:

- Next.js `app/` and `pages/` — every file is a route by convention. A file not linked from anywhere may still be a valid deep link; check `sitemap`, `robots`, and external traffic before deleting.
- React Router / Vue Router — `createBrowserRouter`, `routes.ts`, or `path:` declarations.
- Express / FastAPI / NestJS — route decorators and `app.include_router`.
- Django — `urls.py`; `path()` entries.
- Rails — `config/routes.rb`.
- Go — `net/http` `HandleFunc` calls, or a router library.

Compare the route table against actual navigation: `rg -n 'href="/' src/`, `to="/..."`, `navigate("/...")`, `router.push`. A route with zero inbound links is unreachable from the UI but may still be a public API (a webhook, a health check, a deep link from an email). Check webhooks, third-party integrations, and `fetch("/api/...")` calls before deleting.

## Stale assets

Find assets nothing references:

```bash
rg -n -g '!node_modules' -e '\.png' -e '\.svg' -e '\.woff' src/ public/ index.html
```

Better: list the assets on disk and check each filename against the union of source text, CSS `url()` references, and the manifest. Watch for:

- Fonts referenced only through a CSS `@font-face` with a relative path.
- Icons imported through an icon library that maps name to file.
- Images referenced only from a `manifest.json`, an `og:image` meta tag, or a docs markdown file.
- Source maps and chunks that are outputs, not sources — never delete build artifacts from the repo tree; regenerate them.

## Unused i18n keys

Compare the source catalog against the code:

```bash
rg -n -o "t\(\s*'[^']+'" src/ | sort -u
rg -n -o '"[a-zA-Z0-9_.]+"' src/locales/en.json | sort -u
```

Keys are often built dynamically: `t(\`nav.${item.id}\`)`, `t(section + ".title")`. A static diff will call every key in that section unused. Search for template literals and concatenation near the lookup site before removing anything.

Remove the key from the **source** locale first, then from the translated files. The reverse order breaks fallback during the intermediate commit.

## Commented-out code

```bash
rg -n '^\s*(//|#|/\*|\*)\s*(function|def|class|import|const|let|var|return|if|for|while)\b' .
```

A commented block is dead code only when the feature was actually replaced, not paused. Check git history for the commit that commented it out:

```bash
git log -S 'theCommentedLine' --oneline
```

If the block was commented out because of a bug that may return, keep it in git history (which it already is) and delete it from the working tree. Replace long blocks with a one-line `// TODO(owner): reason` if the reason matters.

## Dynamic-reference pitfalls

These are the cases that defeat static analysis. Grep the **string**, not just the identifier, before removing anything.

| Pattern | Example | How to check |
|---------|---------|--------------|
| Dynamic import | `await import(\`./${name}.js\`)` | Grep for the string form and for the variable's possible values |
| CommonJS require | `require(name)` | Same |
| Python importlib | `importlib.import_module(name)` | Same |
| Webpack context | `require.context('./modules', true, /\.js$/)` | Every file in the directory is reachable |
| Vite glob import | `import.meta.glob('./pages/*.vue')` | Same |
| Vite dynamic import | `import(\`./pages/\${route}.vue\`)` | Same |
| Plugin / extension registry | `plugins: ['a', 'b']` resolved by name | Grep the registry file for the string |
| Framework auto-registration | Django `INSTALLED_APPS`, Spring `@ComponentScan`, Rails `initializers`, Laravel providers | Read the registry, then grep for the class name as a string |
| DI container | `bind(ServiceName)` resolved by type name | Grep the binding string |
| ORM / reflection | Models mapped by class name, `get_model("User")` | Grep for the model name as a string |
| Database migrations | Migration files reference models by name | Never delete a migration or a model a migration touches |
| Seeds and fixtures | `factory.create(User)` or a JSON fixture keyed by name | Grep the fixture directory |
| Serialization | JSON schema, protobuf, GraphQL, OpenAPI — the type name is the wire format | Treat as a public contract |
| Serverless / edge handlers | `functions/*.ts` picked up by file glob | Check the deploy config |
| CLI entry points | `bin` in `package.json`, `console_scripts` in `pyproject.toml`, `[[bin]]` in `Cargo.toml` | Read the manifest |
| Framework file routing | `pages/`, `app/`, `routes/`, `src/views/` | Every file is a route |
| Decorators and metadata | `@app.command`, `@task`, `@celery` | The decorator registers it |
| Test fixtures and parametrize | `@pytest.mark.parametrize("case", [...])` | The name is a string |
| Environment-driven config | `if os.environ.get("FEATURE_X")` | The name is a string in env config |
| Generators and templates | `*.tmpl`, `*.ejs`, `*.jinja` emitted into source | Regenerate; never delete the template |
| Generated code | protobuf, GraphQL, OpenAPI clients, ORM stubs | Regenerate; never delete |
| Re-exports | `export * from './x'`, `__init__.py` imports | Public surface; treat as used |
| String-keyed maps | `{"old_name": handler}` | Grep the string |
| Shell / Makefile / CI | `npm run build:x`, `make target` | Read the scripts |
| Docs and READMEs | A snippet referencing the symbol | Grep the docs |
| Package manifests | `exports`, `files`, `main`, `types`, `sideEffects` | Public API |
| Web workers, service workers, `import.meta.env` | Registered by URL | Grep the URL string |

## Standard false positives

Treat these as "used" unless you have positive proof otherwise.

- Re-exports through `index.ts`, `__init__.py`, or `mod.rs`.
- Names referenced only by a string in a registry, config, or manifest.
- Public API of a published package.
- Test helpers used only by tests that run in a different environment (CI matrix, OS-specific, feature-gated).
- Files matched by a glob (webpack `require.context`, Vite `import.meta.glob`, Docker `COPY`).
- Code called only by a framework (Django `models.py`, Rails `app/models`, Spring `@Entity`, Rails migrations).
- Setters, getters, `__str__`, `__repr__`, lifecycle hooks (`componentDidMount`, `onMount`, `setup`), and interface implementations.
- Serialization models, DTOs, and schema classes.
- ORM entities and migration helpers.
- Constants used through enum-like lookup (`MyEnum.FOO`).
- `main` / `setup` / `teardown` / `beforeEach` hooks.
- Anything referenced only from a comment or docstring — check whether that reference is real.
- Files matched by a build config glob rather than an explicit import.
- Decorator-registered handlers (CLI commands, task queues, event listeners).
- Deprecation shims kept on purpose for backwards compatibility.
- Names shadowed by a local variable in another scope.
- Test snapshots and fixture data.
