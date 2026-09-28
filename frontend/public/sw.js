// Service Worker der installierbaren App. Er haelt nur die Huelle vor
// (index.html und die gebauten Dateien unter /assets), damit die App ohne Netz
// startet. Antworten der API werden nie zwischengespeichert: sie enthalten
// Anschriften und Telefonnummern, und veraltete Spiele waeren schlimmer als
// eine Fehlermeldung.

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
 * Wirft Skripte und Stylesheets weg, die die aktuelle index.html nicht mehr
 * nennt - jedes Release bringt neue. Schriften und Bilder bleiben: sie werden
 * aus dem CSS geladen, stehen also nie in der index.html, und aendern sich kaum.
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

// Seitenaufrufe: immer zuerst das Netz, damit ein Update sofort ankommt.
// Die Huelle aus dem Cache gibt es nur, wenn das Netz fehlt.
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

// Dateien unter /assets tragen einen Hash im Namen und aendern sich nie.
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
