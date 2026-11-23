import {vi} from 'vitest';

/**
 * Ersatz fuer '@/lib/api' in Tests, die nur die Antworten des Servers
 * brauchen. Einbinden mit:
 *
 *     vi.mock('@/lib/api', async () => (await import('@/test/apiMock')).apiModul);
 *
 * Der Test importiert apiGet/apiPost aus diesem Modul und bekommt dieselben
 * Instanzen wie der Code unter Test.
 */
export interface Antwort {
    data: unknown;
}

export const apiGet = vi.fn<(url: string, config?: unknown) => Promise<Antwort>>();
export const apiPost = vi.fn<(url: string, body?: unknown, config?: unknown) => Promise<Antwort>>();

export const apiModul = {api: {get: apiGet, post: apiPost}};

/** Ein Fehler, wie axios ihn mit Serverantwort wirft */
export function apiFehler(status: number, message?: string): Error & {response: {status: number; data: unknown}} {
    return Object.assign(new Error(`Request failed with status code ${status}`), {
        response: {status, data: message ? {error: {message}} : {}},
    });
}

/**
 * Beantwortet GET-Anfragen je URL. Ein Error als Wert wird geworfen, eine
 * Funktion wird bei jedem Aufruf neu ausgewertet. Unbekannte URLs scheitern.
 */
export function getRouten(routen: Record<string, unknown>): void {
    apiGet.mockImplementation(async (url: string) => {
        if (!(url in routen)) throw new Error(`Unerwarteter GET ${url}`);
        const eintrag = routen[url];
        const wert = typeof eintrag === 'function' ? (eintrag as () => unknown)() : eintrag;
        if (wert instanceof Error) throw wert;
        return {data: wert};
    });
}

/** Setzt beide Mocks vollstaendig zurueck (Aufrufe und Implementierung) */
export function apiZuruecksetzen(): void {
    apiGet.mockReset();
    apiPost.mockReset();
}
