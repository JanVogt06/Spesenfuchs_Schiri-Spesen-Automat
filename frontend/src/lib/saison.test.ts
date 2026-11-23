import {beforeEach, describe, expect, it, vi} from 'vitest';
import {apiGet, apiZuruecksetzen, getRouten} from '@/test/apiMock';
import {formatKarte, getSaison, getSaisons, summeKarten, type SaisonSpiel} from './saison';

vi.mock('@/lib/api', async () => (await import('@/test/apiMock')).apiModul);

function spiel(teil: Partial<SaisonSpiel> = {}): SaisonSpiel {
    return {
        id: 1,
        saison: '26/27',
        datum: '2026-09-12',
        uhrzeit: '15:00',
        liga: 'Kreisliga A',
        heim: 'FC Heim',
        gast: 'SV Gast',
        ergebnis: '1:0',
        heim_gelb: null,
        heim_gelbrot: null,
        heim_rot: null,
        gast_gelb: null,
        gast_gelbrot: null,
        gast_rot: null,
        eigene_rolle: 'SR',
        gespann: [],
        ...teil,
    };
}

beforeEach(() => {
    apiZuruecksetzen();
});

describe('formatKarte', () => {
    it('zeigt nicht erfasste Werte als Gedankenstrich', () => {
        expect(formatKarte(null)).toBe('–');
        expect(formatKarte(undefined as unknown as null)).toBe('–');
    });

    it('zeigt Zahlen, auch die Null', () => {
        expect(formatKarte(0)).toBe('0');
        expect(formatKarte(3)).toBe('3');
    });
});

describe('summeKarten', () => {
    it('summiert eine Spalte und zaehlt null als 0', () => {
        const spiele = [spiel({heim_gelb: 2}), spiel({heim_gelb: null}), spiel({heim_gelb: 3})];
        expect(summeKarten(spiele, 'heim_gelb')).toBe(5);
    });

    it('liefert 0 ohne Spiele', () => {
        expect(summeKarten([], 'gast_rot')).toBe(0);
    });

    it('ignoriert Felder, die keine Zahl sind', () => {
        expect(summeKarten([spiel()], 'heim')).toBe(0);
        expect(summeKarten([spiel({id: 7}), spiel({id: 8})], 'id')).toBe(15);
    });
});

describe('Endpunkte', () => {
    it('getSaisons laedt /api/saison', async () => {
        getRouten({'/api/saison': [{saison: '26/27', spiele: 4, letztes_spiel: '2026-10-01', scraped_at: ''}]});
        await expect(getSaisons()).resolves.toHaveLength(1);
        expect(apiGet).toHaveBeenCalledWith('/api/saison');
    });

    it('getSaison kodiert den Schraegstrich im Saisonnamen bewusst nicht', async () => {
        getRouten({'/api/saison/26/27': {saison: '26/27', spiele: [], einsaetze: [], lehrgaenge: null}});
        await expect(getSaison('26/27')).resolves.toMatchObject({saison: '26/27'});
        expect(apiGet).toHaveBeenCalledWith('/api/saison/26/27');
    });
});
