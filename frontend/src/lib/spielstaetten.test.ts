import {beforeEach, describe, expect, it, vi} from 'vitest';
import {apiGet, apiZuruecksetzen, getRouten} from '@/test/apiMock';
import {getSpielstaetten, inSaison, ortPopup, type BesuchterOrt} from './spielstaetten';

vi.mock('@/lib/api', async () => (await import('@/test/apiMock')).apiModul);

const ORT: BesuchterOrt = {
    name: 'Sportplatz <Am> Wald', adresse: 'Waldweg 1, 99999 Irgendwo', lat: 50, lon: 11, genauigkeit: 'platz',
    anzahl: 3,
    spiele: [
        {datum: '2026-10-10', saison: '26/27', heim: 'FC Heim', gast: 'SV Gast', rolle: 'SR'},
        {datum: '2026-03-01', saison: '25/26', heim: 'FC Alt', gast: 'SV Alt', rolle: null},
        {datum: '2025-09-01', saison: '25/26', heim: '', gast: '', rolle: 'SRA 1'},
    ],
};

beforeEach(() => apiZuruecksetzen());

describe('spielstaetten', () => {
    it('laedt die besuchten Plaetze', async () => {
        getRouten({'/api/spielstaetten': {orte: [], offen: 0}});
        await expect(getSpielstaetten()).resolves.toMatchObject({offen: 0});
        expect(apiGet).toHaveBeenCalledWith('/api/spielstaetten');
    });

    it('grenzt auf eine Saison ein und zaehlt neu', () => {
        expect(inSaison([ORT], null)).toEqual([ORT]);
        const nur = inSaison([ORT], '25/26');
        expect(nur[0].anzahl).toBe(2);
        expect(nur[0].spiele.map((s) => s.datum)).toEqual(['2026-03-01', '2025-09-01']);
        expect(inSaison([ORT], '24/25')).toEqual([]);
    });

    it('baut das Popup mit maskiertem Text, Rolle und Turnier', () => {
        const html = ortPopup(ORT);
        expect(html).toContain('Sportplatz &lt;Am&gt; Wald');
        expect(html).toContain('3 Einsätze');
        expect(html).toContain('10.10.2026 · FC Heim – SV Gast · SR');
        expect(html).toContain('01.03.2026 · FC Alt – SV Alt</div>');
        expect(html).toContain('01.09.2025 · Turnier · SRA 1');
        expect(html).not.toContain('Ungefähre Lage');
    });

    it('kuerzt lange Listen und nennt ungefaehre Lagen', () => {
        const viele = {...ORT, genauigkeit: 'ort' as const, anzahl: 8,
            spiele: Array.from({length: 8}, (_, i) => ({...ORT.spiele[0], datum: `2026-10-${10 + i}`}))};
        const html = ortPopup(viele);
        expect(html).toContain('… und 2 weitere');
        expect(html).toContain('Ungefähre Lage');
    });
});
