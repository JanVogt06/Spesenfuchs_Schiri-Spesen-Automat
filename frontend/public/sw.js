// Service worker of the installable app. It only keeps the shell
// (index.html and the built files under /assets) so that the app starts
// without a network. API responses are never cached: they contain
// addresses and phone numbers, and stale matches would be worse than
// an error message.

const CACHE = 'spesenfuchs-v1';
const HUELLE = '/index.html';

self.addEventListener('install', () => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil((async () => {
        const namen = await caches.keys();
        await Promise.all(namen.filter((n) => n !== CACHE).map((n) => caches.delete(n)));
        await self.clients.claim();
    })());
});

/**
 * Discards scripts and stylesheets that the current index.html no longer
 * mentions - every release brings new ones. Fonts and images stay: they are
 * loaded from the CSS, so they never appear in index.html, and rarely change.
 */
async function aufraeumen(html) {
    const cache = await caches.open(CACHE);
    for (const anfrage of await cache.keys()) {
        const pfad = new URL(anfrage.url).pathname;
        if (/^\/assets\/.+\.(js|css)$/.test(pfad) && !html.includes(pfad)) {
            await cache.delete(anfrage);
        }
    }
}

// Page requests: network first, so that an update arrives immediately.
// The shell from the cache is only used when the network is missing.
async function seite(request) {
    try {
        const antwort = await fetch(request);
        if (antwort.ok && (antwort.headers.get('content-type') || '').includes('text/html')) {
            const kopie = antwort.clone();
            const cache = await caches.open(CACHE);
            await cache.put(HUELLE, kopie.clone());
            aufraeumen(await kopie.text());
        }
        return antwort;
    } catch (fehler) {
        const gespeichert = await caches.match(HUELLE);
        if (gespeichert) return gespeichert;
        throw fehler;
    }
}

// Files under /assets carry a hash in their name and never change.
async function asset(request) {
    const gespeichert = await caches.match(request);
    if (gespeichert) return gespeichert;
    const antwort = await fetch(request);
    if (antwort.ok) {
        const cache = await caches.open(CACHE);
        await cache.put(request, antwort.clone());
    }
    return antwort;
}

self.addEventListener('fetch', (event) => {
    const {request} = event;
    if (request.method !== 'GET') return;

    const url = new URL(request.url);
    if (url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;

    if (request.mode === 'navigate') {
        event.respondWith(seite(request));
    } else if (url.pathname.startsWith('/assets/')) {
        event.respondWith(asset(request));
    }
});
