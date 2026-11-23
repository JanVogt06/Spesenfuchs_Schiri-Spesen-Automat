import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {apiGet, apiPost, apiZuruecksetzen, getRouten} from '@/test/apiMock';
import {downloadAttrappe, type DownloadAttrappe} from '@/test/download';
import {
    downloadMatchDocument,
    downloadMatchesAsZip,
    extractApiError,
    getAllMatches,
    getMatchGeo,
    saveMatchExpenses,
    triggerBrowserDownload,
} from './matches';

vi.mock('@/lib/api', async () => (await import('@/test/apiMock')).apiModul);

let download: DownloadAttrappe;

beforeEach(() => {
    apiZuruecksetzen();
    download = downloadAttrappe();
});

afterEach(() => {
    download.aufraeumen();
    vi.useRealTimers();
    vi.unstubAllEnvs();
});

describe('triggerBrowserDownload', () => {
    it('klickt einen Link mit Dateiname und gibt die URL danach frei', () => {
        const blob = new Blob(['inhalt']);

        triggerBrowserDownload(blob, 'Spesen.pdf');

        expect(download.createObjectURL).toHaveBeenCalledWith(blob);
        expect(download.klicks).toEqual([{href: 'blob:test/1', download: 'Spesen.pdf', imDokument: true}]);
        expect(download.revokeObjectURL).toHaveBeenCalledWith('blob:test/1');
        // Erst nach dem Klick freigeben, sonst laedt der Browser nichts
        expect(download.revokeObjectURL.mock.invocationCallOrder[0])
            .toBeGreaterThan(download.createObjectURL.mock.invocationCallOrder[0]);
    });

    it('raeumt den Link wieder aus dem Dokument', () => {
        triggerBrowserDownload(new Blob(['x']), 'a.docx');
        expect(document.querySelectorAll('a')).toHaveLength(0);
    });
});

describe('extractApiError', () => {
    it('liest die Meldung aus einem JSON-Blob', async () => {
        const blob = new Blob([JSON.stringify({error: {message: 'Spiel nicht gefunden'}})], {type: 'application/json'});
        await expect(extractApiError({response: {data: blob}}, 'Fallback')).resolves.toBe('Spiel nicht gefunden');
    });

    it('liest die Meldung aus einem gewoehnlichen Objekt', async () => {
        await expect(extractApiError({response: {data: {error: {message: 'Kaputt'}}}}, 'Fallback'))
            .resolves.toBe('Kaputt');
    });

    it('nimmt detail, wenn es keine error.message gibt', async () => {
        await expect(extractApiError({response: {data: {detail: 'Nicht erlaubt'}}}, 'Fallback'))
            .resolves.toBe('Nicht erlaubt');
    });

    it.each([
        ['ohne Antwort', new Error('Network Error')],
        ['ohne Daten', {response: {}}],
        ['bei null', null],
        ['bei leerem Objekt', {response: {data: {}}}],
        ['bei kaputtem JSON', {response: {data: new Blob(['<html>Bad Gateway</html>'])}}],
    ])('liefert den Fallback %s', async (_name, fehler) => {
        await expect(extractApiError(fehler, 'Fallback')).resolves.toBe('Fallback');
    });
});

describe('Endpunkte', () => {
    it('getAllMatches laedt /api/matches', async () => {
        getRouten({'/api/matches': [{_id: 1}]});
        await expect(getAllMatches()).resolves.toEqual([{_id: 1}]);
    });

    it('getMatchGeo laedt die Karte eines Spiels', async () => {
        getRouten({'/api/matches/42/geo': {punkte: [], ohne_treffer: [], gestoert: false}});
        await expect(getMatchGeo(42)).resolves.toMatchObject({gestoert: false});
        expect(apiGet).toHaveBeenCalledWith('/api/matches/42/geo');
    });

    it('saveMatchExpenses schickt die Spiel-ID flach mit den Werten', async () => {
        apiPost.mockResolvedValue({data: {success: true, filename: 'x', expenses: {sr_km: 30}}});

        const ergebnis = await saveMatchExpenses(7, {sr_km: 30, sra1_oevm: null});

        expect(apiPost).toHaveBeenCalledWith('/api/matches/expenses', {match_id: 7, sr_km: 30, sra1_oevm: null});
        expect(ergebnis.success).toBe(true);
    });

    it('downloadMatchDocument laedt als Blob und speichert unter dem Dateinamen', async () => {
        const blob = new Blob(['pdf']);
        apiGet.mockResolvedValue({data: blob});

        await downloadMatchDocument(3, 'pdf', 'Spesen_3.pdf');

        expect(apiGet).toHaveBeenCalledWith('/api/matches/3/download/pdf', {responseType: 'blob'});
        expect(download.createObjectURL).toHaveBeenCalledWith(blob);
        expect(download.klicks[0].download).toBe('Spesen_3.pdf');
    });

    it('downloadMatchesAsZip schickt die Auswahl und nennt die Datei nach dem Tag', async () => {
        vi.stubEnv('TZ', 'Europe/Berlin');
        vi.useFakeTimers({toFake: ['Date']});
        vi.setSystemTime(new Date(2026, 10, 23, 12, 0));
        apiPost.mockResolvedValue({data: new Blob(['zip'])});

        await downloadMatchesAsZip([1, 2]);

        expect(apiPost).toHaveBeenCalledWith(
            '/api/matches/download',
            {match_ids: [1, 2], file_format: 'both'},
            {responseType: 'blob'},
        );
        expect(download.klicks[0].download).toBe('Spesen_2026-11-23.zip');
    });

    it('downloadMatchesAsZip reicht das gewaehlte Format durch', async () => {
        apiPost.mockResolvedValue({data: new Blob(['zip'])});
        await downloadMatchesAsZip([5], 'docx');
        expect(apiPost.mock.calls[0][1]).toEqual({match_ids: [5], file_format: 'docx'});
    });

    // Der Dateiname nimmt das lokale Datum, nicht UTC: wer in Deutschland kurz
    // nach Mitternacht herunterlaedt, bekommt sonst das Datum von gestern.
    it('downloadMatchesAsZip nimmt kurz nach Mitternacht das lokale Datum', async () => {
        vi.stubEnv('TZ', 'Europe/Berlin');
        vi.useFakeTimers({toFake: ['Date']});
        // 23.11.2026, 00:30 in Berlin = 22.11.2026, 23:30 UTC
        vi.setSystemTime(new Date('2026-11-22T23:30:00Z'));
        apiPost.mockResolvedValue({data: new Blob(['zip'])});

        await downloadMatchesAsZip([1]);

        expect(download.klicks[0].download).toBe('Spesen_2026-11-23.zip');
    });
});
