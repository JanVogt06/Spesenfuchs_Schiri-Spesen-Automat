import {vi} from 'vitest';

/**
 * Replacement for '@/lib/api' in tests that only need the server's
 * responses. Include with:
 *
 *     vi.mock('@/lib/api', async () => (await import('@/test/apiMock')).apiModul);
 *
 * The test imports apiGet/apiPost from this module and gets the same
 * instances as the code under test.
 */
export interface Antwort {
    data: unknown;
}

export const apiGet = vi.fn<(url: string, config?: unknown) => Promise<Antwort>>();
export const apiPost = vi.fn<(url: string, body?: unknown, config?: unknown) => Promise<Antwort>>();

export const apiModul = {api: {get: apiGet, post: apiPost}};

/** An error as axios throws it with a server response */
export function apiFehler(status: number, message?: string): Error & {response: {status: number; data: unknown}} {
    return Object.assign(new Error(`Request failed with status code ${status}`), {
        response: {status, data: message ? {error: {message}} : {}},
    });
}

/**
 * Answers GET requests per URL. An Error as a value is thrown, a
 * function is re-evaluated on every call. Unknown URLs fail.
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

/** Resets both mocks completely (calls and implementation) */
export function apiZuruecksetzen(): void {
    apiGet.mockReset();
    apiPost.mockReset();
}
