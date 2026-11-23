import {beforeEach, describe, expect, it, vi} from 'vitest';
import {apiGet, apiZuruecksetzen, getRouten} from '@/test/apiMock';
import {getLigen, tordifferenz, type Tabellenplatz} from './ligen';

vi.mock('@/lib/api', async () => (await import('@/test/apiMock')).apiModul);

function platz(tore: number, gegentore: number): Tabellenplatz {
    return {
        platz: 1, mannschaft: 'FC Test', team_id: 'X1', spiele: 10, siege: 5,
        unentschieden: 3, niederlagen: 2, tore, gegentore, punkte: 18,
    };
}

beforeEach(() => {
    apiZuruecksetzen();
});

describe('tordifferenz', () => {
    it('setzt ein Plus vor positive Differenzen', () => {
        expect(tordifferenz(platz(25, 10))).toBe('+15');
    });

    it('zeigt negative Differenzen mit Minus', () => {
        expect(tordifferenz(platz(8, 20))).toBe('-12');
    });

    it('zeigt eine ausgeglichene Bilanz ohne Vorzeichen', () => {
        expect(tordifferenz(platz(12, 12))).toBe('0');
    });
});

describe('getLigen', () => {
    it('laedt /api/ligen', async () => {
        const antwort = {bestand: {staffeln: 0, mannschaften: 0, aktualisiert_at: null}, staffeln: []};
        getRouten({'/api/ligen': antwort});

        await expect(getLigen()).resolves.toEqual(antwort);
        expect(apiGet).toHaveBeenCalledWith('/api/ligen');
    });
});
