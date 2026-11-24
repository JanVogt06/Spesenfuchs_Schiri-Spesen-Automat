import {describe, expect, it} from 'vitest';
import type {MatchData} from './matches';
import {anstoss, heuteIso, nachMonat, passtZurSuche, teileSpiele} from './spieleliste';

let naechsteId = 1;

function spiel(datum: string | undefined, anpfiff = '', info: MatchData['spiel_info'] = {}, ort = ''): MatchData {
    return {
        _id: naechsteId++,
        _datum: datum,
        spiel_info: {heim_team: 'FC Heim', gast_team: 'SV Gast', anpfiff, ...info},
        schiedsrichter: [],
        spielstaette: ort ? {name: ort} : {},
    };
}

const ids = (liste: MatchData[]) => liste.map((m) => m._datum + (m.spiel_info.anpfiff ? ` ${anstoss(m)}` : ''));

describe('heuteIso', () => {
    it('schreibt das lokale Datum mit fuehrenden Nullen', () => {
        expect(heuteIso(new Date(2026, 0, 5, 23, 59))).toBe('2026-01-05');
    });
});

describe('teileSpiele', () => {
    it('zeigt kommende ab heute aufsteigend, vergangene absteigend', () => {
        const {kommend, vergangen} = teileSpiele([
            spiel('2026-11-30'), spiel('2026-11-01'), spiel('2026-11-24', '18:00'),
            spiel('2026-11-24', '14:30'), spiel('2026-10-12'),
        ], '2026-11-24');

        expect(ids(kommend)).toEqual(['2026-11-24 14:30', '2026-11-24 18:00', '2026-11-30']);
        expect(ids(vergangen)).toEqual(['2026-11-01', '2026-10-12']);
    });

    it('stellt Spiele ohne Datum ans Ende der vergangenen', () => {
        const {kommend, vergangen} = teileSpiele([spiel(undefined), spiel('2026-09-01'), spiel('2026-12-01')], '2026-11-24');

        expect(ids(kommend)).toEqual(['2026-12-01']);
        expect(ids(vergangen)).toEqual(['2026-09-01', 'undefined']);
    });
});

describe('passtZurSuche', () => {
    const treffer = spiel('2026-11-30', '', {heim_team: 'FC Carl Zeiss Jena II', spielklasse: 'Thüringenliga'}, 'Sportplatz Ilmenau');

    it('findet ohne Suchbegriff alles', () => {
        expect(passtZurSuche(treffer, '   ')).toBe(true);
    });

    it('sucht in Vereinen, Spielklasse und Spielstaette ohne Ruecksicht auf Gross-/Kleinschreibung', () => {
        expect(passtZurSuche(treffer, 'zeiss')).toBe(true);
        expect(passtZurSuche(treffer, 'THÜRINGEN')).toBe(true);
        expect(passtZurSuche(treffer, 'ilmenau')).toBe(true);
        expect(passtZurSuche(treffer, 'erfurt')).toBe(false);
    });

    it('verlangt jedes Wort, egal in welchem Feld', () => {
        expect(passtZurSuche(treffer, 'jena ilmenau')).toBe(true);
        expect(passtZurSuche(treffer, 'jena erfurt')).toBe(false);
    });
});

describe('nachMonat', () => {
    it('fasst nach Monat zusammen und behaelt die Reihenfolge', () => {
        const gruppen = nachMonat([spiel('2026-11-30'), spiel('2026-11-02'), spiel('2026-10-12'), spiel(undefined)]);

        expect(gruppen.map((g) => [g.titel, g.spiele.length])).toEqual([
            ['November 2026', 2], ['Oktober 2026', 1], ['Ohne Datum', 1],
        ]);
    });

    it('liefert fuer keine Spiele keine Gruppe', () => {
        expect(nachMonat([])).toEqual([]);
    });
});
