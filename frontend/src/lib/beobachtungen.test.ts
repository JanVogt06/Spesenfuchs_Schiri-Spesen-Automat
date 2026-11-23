import {beforeEach, describe, expect, it, vi} from 'vitest';
import {apiGet, apiZuruecksetzen, getRouten} from '@/test/apiMock';
import {
    angeboteneSaisons,
    formatDatum,
    formatSchnitt,
    getBeobachtungen,
    nachStaffel,
    ROLLEN_GRUPPEN,
    ROLLEN_NAMEN,
    saisonVonDatum,
    schnitte,
    type Beobachtung,
    type BeobachtungsDaten,
    type BeobachtungsRolle,
    type GeleseneSaison,
} from './beobachtungen';

vi.mock('@/lib/api', async () => (await import('@/test/apiMock')).apiModul);

let naechsteId = 1;

function beobachtung(teil: Partial<Beobachtung> = {}): Beobachtung {
    return {
        id: naechsteId++,
        quelle: 'herren',
        saison: '25/26',
        datum: '2025-09-20',
        uhrzeit: '15:00',
        spieltag: '5',
        staffel: 'Landesliga Nord',
        heim: 'FC Heim',
        gast: 'SV Gast',
        ergebnis: '2:1',
        rolle: 'SR',
        note: 8.4,
        note_text: '8,4',
        beobachter: 'Max Beobachter',
        freigegeben_am: '2025-09-25',
        ...teil,
    };
}

function gelesen(saison: string, quelle: GeleseneSaison['quelle'] = 'herren'): GeleseneSaison {
    return {quelle, saison, anzahl: 0, scraped_at: '2026-01-01T00:00:00'};
}

beforeEach(() => {
    apiZuruecksetzen();
});

describe('ROLLEN_GRUPPEN und ROLLEN_NAMEN', () => {
    it('ordnen jede Rolle genau einer Gruppe zu', () => {
        const alleRollen = Object.keys(ROLLEN_NAMEN) as BeobachtungsRolle[];
        const zugeordnet = ROLLEN_GRUPPEN.flatMap((g) => g.rollen);

        expect([...zugeordnet].sort()).toEqual([...alleRollen].sort());
        expect(new Set(zugeordnet).size).toBe(zugeordnet.length);
    });

    it('haben eindeutige Gruppen mit Beschriftung', () => {
        const gruppen = ROLLEN_GRUPPEN.map((g) => g.gruppe);
        expect(new Set(gruppen).size).toBe(gruppen.length);
        ROLLEN_GRUPPEN.forEach((g) => expect(g.label).not.toBe(''));
    });

    it('fassen SRA1 und SRA2 als Assistent zusammen', () => {
        expect(ROLLEN_GRUPPEN.find((g) => g.gruppe === 'assistent')?.rollen).toEqual(['SRA1', 'SRA2']);
        expect(ROLLEN_NAMEN.SRA1).toBe('SRA 1');
        expect(ROLLEN_NAMEN['4OF']).toBe('4. Offizieller');
    });
});

describe('schnitte', () => {
    it('liefert fuer eine leere Liste nichts', () => {
        expect(schnitte([])).toEqual([]);
    });

    it('bildet je Rollengruppe den Durchschnitt in fester Reihenfolge', () => {
        const ergebnis = schnitte([
            beobachtung({rolle: '4OF', note: 8.0}),
            beobachtung({rolle: 'SRA2', note: 8.6}),
            beobachtung({rolle: 'SR', note: 8.2}),
            beobachtung({rolle: 'SRA1', note: 8.4}),
            beobachtung({rolle: 'SR', note: 8.5}),
        ]);

        expect(ergebnis.map((s) => s.gruppe)).toEqual(['sr', 'assistent', 'vierter']);
        expect(ergebnis[0]).toMatchObject({label: 'Schiedsrichter', anzahl: 2});
        expect(ergebnis[0].schnitt).toBeCloseTo(8.35);
        expect(ergebnis[1]).toMatchObject({label: 'Assistent', anzahl: 2});
        expect(ergebnis[1].schnitt).toBeCloseTo(8.5);
        expect(ergebnis[2]).toEqual({gruppe: 'vierter', label: '4. Offizieller', schnitt: 8.0, anzahl: 1});
    });

    it('laesst Gruppen ohne Note weg', () => {
        const ergebnis = schnitte([beobachtung({rolle: 'SRA1', note: 8.3})]);
        expect(ergebnis).toEqual([{gruppe: 'assistent', label: 'Assistent', schnitt: 8.3, anzahl: 1}]);
    });
});

describe('nachStaffel', () => {
    it('gruppiert in der Reihenfolge des ersten Auftretens', () => {
        const a1 = beobachtung({staffel: 'Oberliga'});
        const b1 = beobachtung({staffel: 'Landesliga'});
        const a2 = beobachtung({staffel: 'Oberliga'});

        expect(nachStaffel([a1, b1, a2])).toEqual([
            {staffel: 'Oberliga', beobachtungen: [a1, a2]},
            {staffel: 'Landesliga', beobachtungen: [b1]},
        ]);
    });

    it('fasst Beobachtungen ohne Staffel unter "Ohne Staffel" zusammen', () => {
        const ohne = beobachtung({staffel: ''});
        expect(nachStaffel([ohne])).toEqual([{staffel: 'Ohne Staffel', beobachtungen: [ohne]}]);
    });

    it('liefert fuer eine leere Liste nichts', () => {
        expect(nachStaffel([])).toEqual([]);
    });
});

describe('saisonVonDatum', () => {
    it.each([
        ['26.01.2019', '18/19'],
        ['30.06.2019', '18/19'],
        ['01.07.2019', '19/20'],
        ['31.12.2025', '25/26'],
        ['15.08.2009', '09/10'],
        ['01.07.1999', '99/00'],
        ['  01.08.2020  ', '20/21'],
    ])('%s -> %s', (datum, saison) => {
        expect(saisonVonDatum(datum)).toBe(saison);
    });

    it.each([null, '', '2019-01-26', '1.1.2019', 'unbekannt'])('liefert null fuer %j', (datum) => {
        expect(saisonVonDatum(datum)).toBeNull();
    });
});

describe('angeboteneSaisons', () => {
    function daten(teil: Partial<BeobachtungsDaten>): BeobachtungsDaten {
        return {schiedsrichter_seit: null, saisons: [], beobachtungen: [], ...teil};
    }

    it('bietet gelesene Herren-Saisons ab "Schiedsrichter seit" an, neueste zuerst', () => {
        const ergebnis = angeboteneSaisons(daten({
            schiedsrichter_seit: '15.08.2021',
            saisons: [gelesen('20/21'), gelesen('22/23'), gelesen('21/22'), gelesen('25/26')],
        }));

        expect(ergebnis).toEqual(['25/26', '22/23', '21/22']);
    });

    it('nimmt ohne "Schiedsrichter seit" jede gelesene Herren-Saison', () => {
        const ergebnis = angeboteneSaisons(daten({saisons: [gelesen('10/11'), gelesen('24/25')]}));
        expect(ergebnis).toEqual(['24/25', '10/11']);
    });

    it('nimmt Portal-Saisons nur, wenn es dort Beobachtungen gibt', () => {
        const ergebnis = angeboteneSaisons(daten({
            saisons: [gelesen('23/24', 'portal'), gelesen('24/25', 'portal')],
            beobachtungen: [beobachtung({quelle: 'portal', saison: '24/25'})],
        }));

        expect(ergebnis).toEqual(['24/25']);
    });

    it('zeigt Saisons mit Beobachtungen auch vor "Schiedsrichter seit"', () => {
        const ergebnis = angeboteneSaisons(daten({
            schiedsrichter_seit: '01.08.2024',
            saisons: [gelesen('23/24'), gelesen('24/25')],
            beobachtungen: [beobachtung({saison: '23/24'})],
        }));

        expect(ergebnis).toEqual(['24/25', '23/24']);
    });

    it('liefert jede Saison nur einmal und sortiert Unbekanntes ans Ende', () => {
        const ergebnis = angeboteneSaisons(daten({
            saisons: [gelesen('24/25')],
            beobachtungen: [
                beobachtung({saison: 'Altbestand'}),
                beobachtung({saison: '24/25'}),
                beobachtung({saison: '25/26'}),
            ],
        }));

        expect(ergebnis).toEqual(['25/26', '24/25', 'Altbestand']);
    });

    it('liefert ohne Daten eine leere Liste', () => {
        expect(angeboteneSaisons(daten({}))).toEqual([]);
    });
});

describe('formatSchnitt', () => {
    it.each([
        [243.375, '243,38'],
        [8.4, '8,40'],
        [8, '8,00'],
        [8.345, '8,35'],
        [1234.5, '1.234,50'],
    ])('%d -> %s', (wert, text) => {
        expect(formatSchnitt(wert)).toBe(text);
    });
});

describe('formatDatum', () => {
    it('dreht ein ISO-Datum ins deutsche Format', () => {
        expect(formatDatum('2026-09-20')).toBe('20.09.2026');
    });

    it.each(['', '20.09.2026', '2026-09'])('laesst %j unveraendert', (wert) => {
        expect(formatDatum(wert)).toBe(wert);
    });
});

describe('getBeobachtungen', () => {
    it('laedt /api/beobachtungen', async () => {
        const antwort: BeobachtungsDaten = {schiedsrichter_seit: '01.08.2015', saisons: [], beobachtungen: []};
        getRouten({'/api/beobachtungen': antwort});

        await expect(getBeobachtungen()).resolves.toEqual(antwort);
        expect(apiGet).toHaveBeenCalledWith('/api/beobachtungen');
    });
});
