import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {act, renderHook} from '@testing-library/react';
import {apiFehler, apiGet, apiPost, apiZuruecksetzen} from '@/test/apiMock';
import {DFB_STATUS_EVENT} from '@/lib/auth';
import {isRunActive, useScrapeRun, type ScrapeRun} from './useScrapeRun';

vi.mock('@/lib/api', async () => (await import('@/test/apiMock')).apiModul);

function lauf(status: ScrapeRun['status'], step = ''): ScrapeRun {
    return {run_id: 1, status, progress: status === 'idle' ? null : {current: 0, total: 0, step}};
}

/** Der Server antwortet nacheinander mit diesen Staenden; der letzte bleibt stehen */
function statusFolge(...staende: (ScrapeRun | Error)[]) {
    const rest = [...staende];
    apiGet.mockImplementation(async (url: string) => {
        if (url !== '/api/scrape/status') throw new Error(`Unerwarteter GET ${url}`);
        const stand = rest.length > 1 ? rest.shift()! : rest[0];
        if (stand instanceof Error) throw stand;
        return {data: stand};
    });
}

/** Laesst ausstehende Promises und die daraus folgenden Renders durchlaufen */
async function abwarten() {
    await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
    });
}

async function weiter(ms: number) {
    await act(async () => {
        await vi.advanceTimersByTimeAsync(ms);
    });
}

const statusAufrufe = () => apiGet.mock.calls.filter(([url]) => url === '/api/scrape/status').length;

let dfbEvents: ReturnType<typeof vi.fn<(e: Event) => void>>;

beforeEach(() => {
    vi.useFakeTimers();
    apiZuruecksetzen();
    dfbEvents = vi.fn<(e: Event) => void>();
    window.addEventListener(DFB_STATUS_EVENT, dfbEvents);
});

afterEach(() => {
    window.removeEventListener(DFB_STATUS_EVENT, dfbEvents);
    vi.useRealTimers();
});

describe('isRunActive', () => {
    it.each([
        ['pending', true], ['scraping', true], ['generating', true],
        ['idle', false], ['completed', false], ['failed', false],
    ] as const)('%s -> %s', (status, aktiv) => {
        expect(isRunActive(lauf(status))).toBe(aktiv);
    });

    it('gilt ohne Lauf als inaktiv', () => {
        expect(isRunActive(null)).toBe(false);
    });
});

describe('useScrapeRun - Laden und Pollen', () => {
    it('laedt beim Einhaengen einmal den Status', async () => {
        statusFolge(lauf('completed'));
        const {result} = renderHook(() => useScrapeRun());

        expect(result.current.run).toBeNull();
        await abwarten();

        expect(statusAufrufe()).toBe(1);
        expect(result.current.run?.status).toBe('completed');
        expect(result.current.isRunning).toBe(false);
    });

    it('pollt nicht, solange nichts laeuft', async () => {
        statusFolge(lauf('idle'));
        renderHook(() => useScrapeRun());
        await abwarten();

        await weiter(10_000);

        expect(statusAufrufe()).toBe(1);
    });

    it('pollt alle zwei Sekunden, solange ein Lauf aktiv ist, und hoert danach auf', async () => {
        statusFolge(lauf('pending'), lauf('scraping', 'Lese Ansetzungen'), lauf('generating'), lauf('completed'));
        const {result} = renderHook(() => useScrapeRun());
        await abwarten();
        expect(result.current.isRunning).toBe(true);

        await weiter(1999);
        expect(statusAufrufe()).toBe(1);
        await weiter(1);
        expect(statusAufrufe()).toBe(2);
        expect(result.current.run?.progress?.step).toBe('Lese Ansetzungen');

        await weiter(2000);
        await weiter(2000);
        expect(statusAufrufe()).toBe(4);
        expect(result.current.run?.status).toBe('completed');
        expect(result.current.isRunning).toBe(false);

        await weiter(20_000);
        expect(statusAufrufe()).toBe(4);
    });

    it('ruft onFinished genau einmal an der Flanke von laufend nach fertig und meldet den DFB-Status', async () => {
        const onFinished = vi.fn();
        statusFolge(lauf('scraping'), lauf('scraping'), lauf('failed'));
        renderHook(() => useScrapeRun(onFinished));
        await abwarten();

        await weiter(2000);
        expect(onFinished).not.toHaveBeenCalled();
        expect(dfbEvents).not.toHaveBeenCalled();

        await weiter(2000);
        expect(onFinished).toHaveBeenCalledTimes(1);
        expect(dfbEvents).toHaveBeenCalledTimes(1);

        await weiter(10_000);
        expect(onFinished).toHaveBeenCalledTimes(1);
        expect(dfbEvents).toHaveBeenCalledTimes(1);
    });

    it('ruft onFinished nicht, wenn der Lauf schon beim Oeffnen fertig war', async () => {
        const onFinished = vi.fn();
        statusFolge(lauf('completed'));
        const {result} = renderHook(() => useScrapeRun(onFinished));
        await abwarten();

        await act(async () => {
            await result.current.reload();
        });

        expect(onFinished).not.toHaveBeenCalled();
        expect(dfbEvents).not.toHaveBeenCalled();
    });

    it('nimmt immer den neuesten onFinished-Callback, ohne das Polling neu aufzusetzen', async () => {
        const erster = vi.fn();
        const zweiter = vi.fn();
        statusFolge(lauf('scraping'), lauf('completed'));
        const {rerender} = renderHook(({cb}) => useScrapeRun(cb), {initialProps: {cb: erster}});
        await abwarten();

        await weiter(1000);
        rerender({cb: zweiter});
        await weiter(1000);

        expect(statusAufrufe()).toBe(2);
        expect(erster).not.toHaveBeenCalled();
        expect(zweiter).toHaveBeenCalledTimes(1);
    });

    it('protokolliert einen Ladefehler und behaelt den alten Stand', async () => {
        const konsole = vi.spyOn(console, 'error').mockImplementation(() => {});
        statusFolge(new Error('Keine Verbindung'));
        const {result} = renderHook(() => useScrapeRun());
        await abwarten();

        expect(result.current.run).toBeNull();
        expect(konsole).toHaveBeenCalledWith('Status konnte nicht geladen werden:', expect.any(Error));

        let rueckgabe: ScrapeRun | null = lauf('idle');
        await act(async () => {
            rueckgabe = await result.current.reload();
        });
        expect(rueckgabe).toBeNull();
    });

    it('pollt nach einem Ladefehler waehrend eines Laufs weiter', async () => {
        vi.spyOn(console, 'error').mockImplementation(() => {});
        const onFinished = vi.fn();
        statusFolge(lauf('scraping'), new Error('Wackeliges Netz'), lauf('completed'));
        renderHook(() => useScrapeRun(onFinished));
        await abwarten();

        await weiter(2000);
        await weiter(2000);

        expect(statusAufrufe()).toBe(3);
        expect(onFinished).toHaveBeenCalledTimes(1);
    });

    it('stoppt das Polling beim Abbau', async () => {
        statusFolge(lauf('scraping'));
        const {unmount} = renderHook(() => useScrapeRun());
        await abwarten();

        unmount();
        await weiter(10_000);

        expect(statusAufrufe()).toBe(1);
    });
});

describe('useScrapeRun - startGeneration', () => {
    it('startet den Abruf, laedt den Status und meldet das Ende', async () => {
        const onFinished = vi.fn();
        statusFolge(lauf('idle'), lauf('pending'), lauf('completed'));
        let postFertig: (wert: {data: unknown}) => void = () => {};
        apiPost.mockReturnValue(new Promise((resolve) => {
            postFertig = resolve;
        }));
        const {result} = renderHook(() => useScrapeRun(onFinished));
        await abwarten();

        let start: Promise<void> = Promise.resolve();
        act(() => {
            start = result.current.startGeneration();
        });
        expect(result.current.isStarting).toBe(true);
        expect(apiPost).toHaveBeenCalledWith('/api/generate', {});

        await act(async () => {
            postFertig({data: {run_id: 2, status: 'pending'}});
            await start;
        });
        expect(result.current.isStarting).toBe(false);
        expect(result.current.isRunning).toBe(true);
        expect(result.current.error).toBe('');

        await weiter(2000);
        expect(onFinished).toHaveBeenCalledTimes(1);
        expect(dfbEvents).toHaveBeenCalledTimes(1);
        expect(result.current.isRunning).toBe(false);
    });

    it('zeigt die Fehlermeldung des Servers', async () => {
        statusFolge(lauf('idle'));
        apiPost.mockRejectedValue(apiFehler(409, 'Es läuft bereits ein Abruf. Bitte warte, bis er fertig ist.'));
        const {result} = renderHook(() => useScrapeRun());
        await abwarten();

        await act(async () => {
            await result.current.startGeneration();
        });

        expect(result.current.error).toBe('Es läuft bereits ein Abruf. Bitte warte, bis er fertig ist.');
        expect(result.current.isStarting).toBe(false);
    });

    it('faellt ohne Servermeldung auf einen eigenen Text zurueck', async () => {
        statusFolge(lauf('idle'));
        apiPost.mockRejectedValue(new Error('Keine Verbindung zum Server.'));
        const {result} = renderHook(() => useScrapeRun());
        await abwarten();

        await act(async () => {
            await result.current.startGeneration();
        });

        expect(result.current.error).toBe('Die Generierung konnte nicht gestartet werden.');
    });

    it('loescht einen alten Fehler beim naechsten Versuch', async () => {
        statusFolge(lauf('idle'), lauf('pending'));
        apiPost.mockRejectedValueOnce(apiFehler(400, 'Keine DFB-Zugangsdaten hinterlegt'));
        apiPost.mockResolvedValueOnce({data: {}});
        const {result} = renderHook(() => useScrapeRun());
        await abwarten();

        await act(async () => {
            await result.current.startGeneration();
        });
        expect(result.current.error).not.toBe('');

        await act(async () => {
            await result.current.startGeneration();
        });
        expect(result.current.error).toBe('');
        expect(result.current.isRunning).toBe(true);
    });

    // Ist der Lauf beim ersten Status nach dem Start schon vorbei (Prozess
    // sofort gescheitert), muss onFinished trotzdem genau einmal kommen -
    // und ein spaeteres reload() darf es nicht noch einmal ausloesen.
    it('ruft onFinished, auch wenn der Lauf beim ersten Status schon beendet ist', async () => {
        const onFinished = vi.fn();
        statusFolge(lauf('idle'), lauf('failed'));
        apiPost.mockResolvedValue({data: {}});
        const {result} = renderHook(() => useScrapeRun(onFinished));
        await abwarten();

        await act(async () => {
            await result.current.startGeneration();
        });
        await weiter(10_000);
        expect(onFinished).toHaveBeenCalledTimes(1);

        // Ein spaeteres Nachladen darf es nicht noch einmal ausloesen
        await act(async () => {
            await result.current.reload();
        });
        expect(onFinished).toHaveBeenCalledTimes(1);
    });
});
