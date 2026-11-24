import {beforeEach, describe, expect, it, vi} from 'vitest';
import {apiFehler, apiGet, apiPost, apiZuruecksetzen, getRouten} from '@/test/apiMock';
import {getBugReportStatus, sendeBugReport} from './bugreport';

vi.mock('@/lib/api', async () => (await import('@/test/apiMock')).apiModul);

beforeEach(() => {
    apiZuruecksetzen();
});

describe('getBugReportStatus', () => {
    it('laedt /api/bugreport/status', async () => {
        getRouten({'/api/bugreport/status': {verfuegbar: true, empfaenger: 'fehler@example.org'}});

        await expect(getBugReportStatus()).resolves.toEqual({verfuegbar: true, empfaenger: 'fehler@example.org'});
        expect(apiGet).toHaveBeenCalledWith('/api/bugreport/status');
    });
});

describe('sendeBugReport', () => {
    const bericht = {titel: 'Karte leer', beschreibung: 'Keine Punkte', bereich: 'Spiele', schritte: '1. Oeffnen'};

    it('schickt den Bericht unveraendert an /api/bugreport', async () => {
        apiPost.mockResolvedValue({data: {}});

        await expect(sendeBugReport(bericht)).resolves.toBeUndefined();
        expect(apiPost).toHaveBeenCalledWith('/api/bugreport', bericht);
    });

    it('reicht Fehler an das Formular weiter', async () => {
        apiPost.mockRejectedValue(apiFehler(503, 'Kein Postausgang'));

        await expect(sendeBugReport(bericht)).rejects.toMatchObject({response: {status: 503}});
    });
});
