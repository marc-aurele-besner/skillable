# Service worker: strategy and safety rules

A bad service worker is worse than none: it can pin users to a broken version until they clear site data by hand. Follow these rules for both plugin config and hand-written workers.

## Rules

1. **One SW per scope.** Search for existing registrations (`serviceWorker.register`, `ngsw`, `workbox`, plugin config) before adding one. Two SWs fight over the same scope.
2. **Navigations are network-first.** HTML must come from the network when online, with a timeout (3–5 s) and a precached offline page as the fallback. An SPA may fall back to the precached `index.html` shell instead, and must exclude `/api/`, auth callbacks, and file downloads from `navigateFallback`.
3. **Hashed static assets are cache-first** (precached at install). Unhashed assets (`/logo.png`, fonts from a CDN) use stale-while-revalidate with an expiry and a max entry count.
4. **Never cache** responses to non-GET requests, responses with `Cache-Control: private` or `no-store`, authenticated API calls, `Set-Cookie` responses, opaque cross-origin responses (they take up quota and can hide errors), or anything with personal data, unless the user explicitly asks for offline data.
5. **Versioned caches.** Every deploy changes the precache manifest or cache name; `activate` deletes caches the current version does not own. Workbox and the plugins do this already.
6. **Updates are visible.** Default to a "new version available, reload" prompt (`registerType: 'prompt'`). Use `skipWaiting` + `clientsClaim` silently only for apps where a version mismatch between open tabs cannot break anything. Never reload the page without the user's action while they may be typing.
7. **Production only.** Do not register in dev; it caches hot-reload assets and confuses everyone.
8. **The SW file itself is never cached long.** Serve `sw.js` with `Cache-Control: no-cache`. The browser also checks it at most every 24 h regardless.
9. **Ship a kill switch path.** If something goes wrong, deploying a SW that calls `self.registration.unregister()` and deletes all caches recovers every client. Mention it in the PR body for hand-written SWs.

## Minimal hand-written SW

Use when the stack has no plugin, or to fix a broken custom SW. Replace `VERSION` and `PRECACHE` at build time (a postbuild script that hashes the build output) or keep the list short and bump `VERSION` on each deploy.

```js
// sw.js — served from the app root with Cache-Control: no-cache
const VERSION = 'v1';
const SHELL = `shell-${VERSION}`;
const RUNTIME = `runtime-${VERSION}`;
const OFFLINE_URL = '/offline.html';
const PRECACHE = ['/', OFFLINE_URL, '/manifest.webmanifest', '/icons/icon-192.png'];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(SHELL).then((c) => c.addAll(PRECACHE)));
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keep = new Set([SHELL, RUNTIME]);
    for (const key of await caches.keys()) if (!keep.has(key)) await caches.delete(key);
    if (self.registration.navigationPreload) await self.registration.navigationPreload.enable();
    await self.clients.claim();
  })());
});

self.addEventListener('message', (event) => {
  if (event.data?.type === 'SKIP_WAITING') self.skipWaiting();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/')) return;

  if (request.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        return (await event.preloadResponse) || (await fetch(request));
      } catch {
        return (await caches.match(OFFLINE_URL)) || Response.error();
      }
    })());
    return;
  }

  if (['style', 'script', 'image', 'font'].includes(request.destination)) {
    event.respondWith((async () => {
      const cache = await caches.open(RUNTIME);
      const cached = await cache.match(request);
      const network = fetch(request).then((res) => {
        if (res.ok && res.type === 'basic') cache.put(request, res.clone());
        return res;
      }).catch(() => cached);
      return cached || network;
    })());
  }
});
```

Registration with an update prompt, using the app's own toast:

```js
if ('serviceWorker' in navigator && import.meta.env?.PROD !== false) {
  window.addEventListener('load', async () => {
    const reg = await navigator.serviceWorker.register('/sw.js');
    const prompt = (worker) => showUpdateToast(() => worker.postMessage({ type: 'SKIP_WAITING' }));
    if (reg.waiting) prompt(reg.waiting);
    reg.addEventListener('updatefound', () => {
      const w = reg.installing;
      w?.addEventListener('statechange', () => {
        if (w.state === 'installed' && navigator.serviceWorker.controller) prompt(w);
      });
    });
    let reloaded = false;
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      if (!reloaded) { reloaded = true; location.reload(); }
    });
  });
}
```

## Offline page

Small, self-contained (inline CSS, no external fonts), in the app's colors, with the app name, a short "You're offline" message, and a Retry button (`location.reload()`). Precache it. For SPAs, an offline state inside the app (a banner driven by `navigator.onLine` and `online`/`offline` events) is often better than a separate page; offer it.

## Install prompt

```js
let deferred;
window.addEventListener('beforeinstallprompt', (e) => { e.preventDefault(); deferred = e; showInstallButton(); });
window.addEventListener('appinstalled', () => { deferred = null; hideInstallButton(); });
async function install() { if (!deferred) return; deferred.prompt(); await deferred.userChoice; deferred = null; hideInstallButton(); }

const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
const standalone = matchMedia('(display-mode: standalone)').matches || navigator.standalone;
// iOS has no beforeinstallprompt: show a dismissible "Share → Add to Home Screen" hint once when isIOS && !standalone.
```

Never show the install UI on first paint; tie it to engagement (second visit, after a completed action) or a settings/menu entry.
