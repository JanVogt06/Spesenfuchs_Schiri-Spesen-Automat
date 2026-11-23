import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {act, renderHook} from '@testing-library/react';

type PwaModul = typeof import('./pwa');

/**
 * pwa.ts haelt seinen Zustand auf Modulebene und haengt die Listener beim
 * Import an window. Jeder Test holt sich deshalb ein frisches Modul.
 */
async function frischesModul(): Promise<PwaModul> {
    vi.resetModules();
    return import('./pwa');
}

let standalone = false;

function setzeUserAgent(ua: string, touchPunkte = 0) {
    // jsdom kennt maxTouchPoints nicht; beide Werte als eigene Eigenschaften,
    // die afterEach wieder entfernt
    Object.defineProperty(navigator, 'userAgent', {configurable: true, value: ua});
    Object.defineProperty(navigator, 'maxTouchPoints', {configurable: true, value: touchPunkte});
}

/** Ein beforeinstallprompt, wie Chrome es schickt */
function installAngebot() {
    const prompt = vi.fn(async () => {});
    const ereignis = Object.assign(new Event('beforeinstallprompt', {cancelable: true}), {
        prompt,
        userChoice: Promise.resolve({outcome: 'accepted' as const}),
    });
    return {ereignis, prompt};
}

const WINDOWS_CHROME = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36';

beforeEach(() => {
    standalone = false;
    vi.stubGlobal('matchMedia', vi.fn((query: string) => ({
        matches: query === '(display-mode: standalone)' && standalone,
        media: query,
    })));
    setzeUserAgent(WINDOWS_CHROME);
});

afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    const nav = navigator as unknown as Record<string, unknown>;
    for (const name of ['standalone', 'serviceWorker', 'userAgent', 'maxTouchPoints']) delete nav[name];
});

describe('useInstallation - Erkennung', () => {
    it('meldet im normalen Browser-Tab weder Installation noch Angebot', async () => {
        const {useInstallation} = await frischesModul();
        const {result} = renderHook(() => useInstallation());

        expect(result.current).toMatchObject({installiert: false, kannInstallieren: false, ios: false});
    });

    it('erkennt den Standalone-Modus ueber display-mode', async () => {
        standalone = true;
        const {useInstallation} = await frischesModul();
        const {result} = renderHook(() => useInstallation());

        expect(result.current.installiert).toBe(true);
    });

    it('erkennt die Home-Bildschirm-App auf iOS ueber navigator.standalone', async () => {
        Object.defineProperty(navigator, 'standalone', {configurable: true, value: true});
        const {useInstallation} = await frischesModul();
        const {result} = renderHook(() => useInstallation());

        expect(result.current.installiert).toBe(true);
    });

    it.each([
        ['iPhone', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile Safari/604.1', 5, true],
        ['iPad (alt)', 'Mozilla/5.0 (iPad; CPU OS 16_0 like Mac OS X) AppleWebKit/605.1.15', 5, true],
        ['iPadOS als Mac mit Touch', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/18.0 Safari/605.1.15', 5, true],
        ['echter Mac', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/18.0 Safari/605.1.15', 0, false],
        ['Android', 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/130.0 Mobile Safari/537.36', 5, false],
        ['Windows', WINDOWS_CHROME, 0, false],
    ])('erkennt iOS: %s', async (_name, ua, touch, ios) => {
        setzeUserAgent(ua, touch);
        const {useInstallation} = await frischesModul();
        const {result} = renderHook(() => useInstallation());

        expect(result.current.ios).toBe(ios);
    });
});

describe('useInstallation - Installationsdialog', () => {
    it('bietet nach beforeinstallprompt die Installation an und unterdrueckt Chromes Leiste', async () => {
        const {useInstallation} = await frischesModul();
        const {result} = renderHook(() => useInstallation());
        const {ereignis} = installAngebot();

        act(() => {
            window.dispatchEvent(ereignis);
        });

        expect(ereignis.defaultPrevented).toBe(true);
        expect(result.current.kannInstallieren).toBe(true);
        expect(result.current.installiert).toBe(false);
    });

    it('merkt sich ein Angebot, das vor dem ersten Rendern kam', async () => {
        const {useInstallation} = await frischesModul();
        window.dispatchEvent(installAngebot().ereignis);

        const {result} = renderHook(() => useInstallation());

        expect(result.current.kannInstallieren).toBe(true);
    });

    it('zeigt den Dialog genau einmal; danach ist das Angebot verbraucht', async () => {
        const {useInstallation} = await frischesModul();
        const {result} = renderHook(() => useInstallation());
        const {ereignis, prompt} = installAngebot();
        act(() => {
            window.dispatchEvent(ereignis);
        });

        await act(async () => {
            await result.current.installieren();
        });

        expect(prompt).toHaveBeenCalledTimes(1);
        expect(result.current.kannInstallieren).toBe(false);

        await act(async () => {
            await result.current.installieren();
        });
        expect(prompt).toHaveBeenCalledTimes(1);
    });

    it('tut ohne Angebot nichts', async () => {
        const {useInstallation} = await frischesModul();
        const {result} = renderHook(() => useInstallation());

        await act(async () => {
            await expect(result.current.installieren()).resolves.toBeUndefined();
        });
        expect(result.current.kannInstallieren).toBe(false);
    });

    it('meldet nach appinstalled die Installation und zieht das Angebot zurueck', async () => {
        const {useInstallation} = await frischesModul();
        const {result} = renderHook(() => useInstallation());
        act(() => {
            window.dispatchEvent(installAngebot().ereignis);
        });

        act(() => {
            window.dispatchEvent(new Event('appinstalled'));
        });

        expect(result.current.installiert).toBe(true);
        expect(result.current.kannInstallieren).toBe(false);
    });
});

describe('registriereServiceWorker', () => {
    /**
     * Faengt den load-Listener ab, statt ihn an window zu haengen - sonst
     * liefe er in spaeteren Tests mit, wenn deren Seite "laedt".
     */
    function ladeListener(): {laden: () => void; angemeldet: () => boolean} {
        const listener: EventListener[] = [];
        vi.spyOn(window, 'addEventListener').mockImplementation((typ: string, hoerer: EventListenerOrEventListenerObject | null) => {
            if (typ === 'load' && typeof hoerer === 'function') listener.push(hoerer);
        });
        return {
            laden: () => listener.forEach((h) => h(new Event('load'))),
            angemeldet: () => listener.length > 0,
        };
    }

    it('registriert im Dev-Server keinen Worker', async () => {
        const register = vi.fn(async () => ({}));
        Object.defineProperty(navigator, 'serviceWorker', {configurable: true, value: {register}});
        const {registriereServiceWorker} = await frischesModul();
        const seite = ladeListener();

        registriereServiceWorker();
        seite.laden();

        expect(seite.angemeldet()).toBe(false);
        expect(register).not.toHaveBeenCalled();
    });

    it('registriert im Build /sw.js, sobald die Seite geladen ist', async () => {
        vi.stubEnv('PROD', true);
        const register = vi.fn(async () => ({}));
        Object.defineProperty(navigator, 'serviceWorker', {configurable: true, value: {register}});
        const {registriereServiceWorker} = await frischesModul();
        const seite = ladeListener();

        registriereServiceWorker();
        expect(register).not.toHaveBeenCalled();
        seite.laden();

        expect(register).toHaveBeenCalledWith('/sw.js');
    });

    it('faengt eine gescheiterte Registrierung ab', async () => {
        vi.stubEnv('PROD', true);
        const abgelehnt = Promise.reject(new Error('SecurityError'));
        const fangen = vi.spyOn(abgelehnt, 'catch');
        const register = vi.fn(() => abgelehnt);
        Object.defineProperty(navigator, 'serviceWorker', {configurable: true, value: {register}});
        const {registriereServiceWorker} = await frischesModul();
        const seite = ladeListener();

        registriereServiceWorker();
        seite.laden();
        await expect(fangen.mock.results[0].value).resolves.toBeUndefined();

        expect(register).toHaveBeenCalled();
        expect(fangen).toHaveBeenCalledTimes(1);
    });

    it('tut ohne Service-Worker-Unterstuetzung nichts', async () => {
        vi.stubEnv('PROD', true);
        const {registriereServiceWorker} = await frischesModul();
        const seite = ladeListener();

        registriereServiceWorker();

        expect(seite.angemeldet()).toBe(false);
    });
});
