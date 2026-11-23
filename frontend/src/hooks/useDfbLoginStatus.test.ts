import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {act, renderHook, waitFor} from '@testing-library/react';
import {apiGet, apiZuruecksetzen} from '@/test/apiMock';
import {meldeDfbStatusGeaendert} from '@/lib/auth';
import {useDfbLoginStatus} from './useDfbLoginStatus';

vi.mock('@/lib/api', async () => (await import('@/test/apiMock')).apiModul);

const SEIT = '2026-11-20T03:15:00';

function user(abgelehntSeit: string | null | undefined) {
    return {
        data: {user_id: 1, email: 'sr@example.org', has_dfb_credentials: true, dfb_login_abgelehnt_seit: abgelehntSeit},
    };
}

let sichtbarkeit: DocumentVisibilityState = 'visible';

function wechsleSichtbarkeit(zustand: DocumentVisibilityState) {
    sichtbarkeit = zustand;
    document.dispatchEvent(new Event('visibilitychange'));
}

beforeEach(() => {
    apiZuruecksetzen();
    sichtbarkeit = 'visible';
    Object.defineProperty(document, 'visibilityState', {configurable: true, get: () => sichtbarkeit});
});

afterEach(() => {
    delete (document as unknown as Record<string, unknown>).visibilityState;
});

describe('useDfbLoginStatus', () => {
    it('laedt /api/auth/me und liefert das Datum der Ablehnung', async () => {
        apiGet.mockResolvedValue(user(SEIT));
        const {result} = renderHook(() => useDfbLoginStatus());

        expect(result.current).toBeNull();
        await waitFor(() => expect(result.current).toBe(SEIT));
        expect(apiGet).toHaveBeenCalledWith('/api/auth/me');
    });

    it.each([null, undefined])('liefert null, wenn DFBnet die Daten annimmt (%j)', async (wert) => {
        apiGet.mockResolvedValue(user(wert));
        const {result} = renderHook(() => useDfbLoginStatus());

        await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(1));
        await act(async () => {});
        expect(result.current).toBeNull();
    });

    it('laedt nach DFB_STATUS_EVENT neu', async () => {
        apiGet.mockResolvedValueOnce(user(SEIT)).mockResolvedValueOnce(user(null));
        const {result} = renderHook(() => useDfbLoginStatus());
        await waitFor(() => expect(result.current).toBe(SEIT));

        act(() => meldeDfbStatusGeaendert());

        await waitFor(() => expect(result.current).toBeNull());
        expect(apiGet).toHaveBeenCalledTimes(2);
    });

    it('laedt neu, wenn die App wieder sichtbar wird', async () => {
        apiGet.mockResolvedValueOnce(user(null)).mockResolvedValueOnce(user(SEIT));
        const {result} = renderHook(() => useDfbLoginStatus());
        await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(1));

        act(() => wechsleSichtbarkeit('hidden'));
        expect(apiGet).toHaveBeenCalledTimes(1);

        act(() => wechsleSichtbarkeit('visible'));
        await waitFor(() => expect(result.current).toBe(SEIT));
        expect(apiGet).toHaveBeenCalledTimes(2);
    });

    it('ignoriert Fehler und behaelt den letzten Stand', async () => {
        apiGet.mockResolvedValueOnce(user(SEIT)).mockRejectedValueOnce(new Error('Keine Verbindung'));
        const {result} = renderHook(() => useDfbLoginStatus());
        await waitFor(() => expect(result.current).toBe(SEIT));

        act(() => meldeDfbStatusGeaendert());
        await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(2));
        await act(async () => {});

        expect(result.current).toBe(SEIT);
    });

    it('zeigt bei einem Fehler gleich zu Beginn keinen Hinweis', async () => {
        apiGet.mockRejectedValue(new Error('500'));
        const {result} = renderHook(() => useDfbLoginStatus());

        await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(1));
        await act(async () => {});
        expect(result.current).toBeNull();
    });

    it('setzt nach dem Abbau keinen Zustand mehr und hoert nicht mehr zu', async () => {
        let antworten: (wert: ReturnType<typeof user>) => void = () => {};
        apiGet.mockReturnValueOnce(new Promise((resolve) => {
            antworten = resolve;
        }));
        const konsole = vi.spyOn(console, 'error');
        const {result, unmount} = renderHook(() => useDfbLoginStatus());

        unmount();
        await act(async () => {
            antworten(user(SEIT));
        });

        expect(result.current).toBeNull();
        expect(konsole).not.toHaveBeenCalled();

        meldeDfbStatusGeaendert();
        wechsleSichtbarkeit('visible');
        expect(apiGet).toHaveBeenCalledTimes(1);
    });
});
