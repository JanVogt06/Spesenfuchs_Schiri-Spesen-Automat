import {useSyncExternalStore} from 'react';

/**
 * Chrome, Edge und Samsung Internet melden per `beforeinstallprompt`, dass
 * sich die Seite installieren laesst. Das Ereignis kommt einmal kurz nach dem
 * Laden - deshalb haengt der Listener hier auf Modulebene und dieses Modul wird
 * in main.tsx vor dem ersten Rendern importiert.
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
    // Unterdrueckt Chromes eigene Leiste; angeboten wird ueber unseren Button
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
    // Im Dev-Server wuerde ein Worker veraltete Module ausliefern
    if (!import.meta.env.PROD || !('serviceWorker' in navigator)) return;
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js').catch(() => {
            // Ohne Worker laeuft die Seite normal weiter, nur nicht offline
        });
    });
}

/** Ob die Seite gerade als installierte App laeuft */
function laeuftAlsApp(): boolean {
    return window.matchMedia('(display-mode: standalone)').matches
        || (navigator as Navigator & {standalone?: boolean}).standalone === true;
}

/**
 * iPhone und iPad. Dort gibt es kein `beforeinstallprompt`, installiert wird nur
 * von Hand ueber "Teilen > Zum Home-Bildschirm". iPadOS meldet sich als Mac,
 * verraet sich aber durch den Touchscreen.
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
    /** Laeuft bereits als App oder wurde gerade installiert */
    installiert: boolean;
    /** Der Browser bietet einen Installationsdialog an */
    kannInstallieren: boolean;
    /** Installation nur von Hand ueber das Teilen-Menue */
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
            // Ein Ereignis laesst sich nur einmal zeigen, danach ist es verbraucht
            wartend = null;
            melden();
        },
    };
}
