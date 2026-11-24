import {useSyncExternalStore} from 'react';

/**
 * Chrome, Edge and Samsung Internet report via `beforeinstallprompt` that
 * the page can be installed. The event comes once shortly after
 * loading - that is why the listener sits at module level here and this module is
 * imported in main.tsx before the first render.
 */
interface BeforeInstallPromptEvent extends Event {
    prompt(): Promise<void>;
    userChoice: Promise<{outcome: 'accepted' | 'dismissed'}>;
}

let wartend: BeforeInstallPromptEvent | null = null;
let installiert = false;
const hoerer = new Set<() => void>();

function melden() {
    hoerer.forEach((h) => h());
}

window.addEventListener('beforeinstallprompt', (e) => {
    // Suppresses Chrome's own bar; installation is offered through our button
    e.preventDefault();
    wartend = e as BeforeInstallPromptEvent;
    melden();
});

window.addEventListener('appinstalled', () => {
    wartend = null;
    installiert = true;
    melden();
});

export function registriereServiceWorker() {
    // In the dev server a worker would serve stale modules
    if (!import.meta.env.PROD || !('serviceWorker' in navigator)) return;
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js').catch(() => {
            // Without a worker the page keeps running normally, just not offline
        });
    });
}

/** Whether the page is currently running as an installed app */
function laeuftAlsApp(): boolean {
    return window.matchMedia('(display-mode: standalone)').matches
        || (navigator as Navigator & {standalone?: boolean}).standalone === true;
}

/**
 * iPhone and iPad. There is no `beforeinstallprompt` there, installation only
 * happens by hand via "Share > Add to Home Screen". iPadOS identifies as a Mac,
 * but gives itself away through the touchscreen.
 */
function istIos(): boolean {
    const ua = navigator.userAgent;
    return /iPhone|iPad|iPod/.test(ua) || (ua.includes('Macintosh') && navigator.maxTouchPoints > 1);
}

function abonnieren(h: () => void) {
    hoerer.add(h);
    return () => {
        hoerer.delete(h);
    };
}

export interface Installation {
    /** Already runs as an app or has just been installed */
    installiert: boolean;
    /** The browser offers an installation dialog */
    kannInstallieren: boolean;
    /** Installation only by hand via the share menu */
    ios: boolean;
    installieren: () => Promise<void>;
}

export function useInstallation(): Installation {
    const angebot = useSyncExternalStore(abonnieren, () => wartend);
    const fertig = useSyncExternalStore(abonnieren, () => installiert);

    return {
        installiert: fertig || laeuftAlsApp(),
        kannInstallieren: angebot !== null,
        ios: istIos(),
        installieren: async () => {
            if (!wartend) return;
            const ereignis = wartend;
            await ereignis.prompt();
            // An event can only be shown once, after that it is consumed
            wartend = null;
            melden();
        },
    };
}
