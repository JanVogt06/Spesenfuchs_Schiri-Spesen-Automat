import {describe, expect, it} from 'vitest';
import {beschreibeFahrgemeinschaft, rollenName, treffpunktLink} from './fahrten';

describe('rollenName', () => {
    it('marks the own role', () => {
        expect(rollenName('sra1', 'sra1')).toBe('SRA 1 (du)');
        expect(rollenName('sr', 'sra1')).toBe('SR');
        expect(rollenName('sra2', null)).toBe('SRA 2');
    });
});

describe('beschreibeFahrgemeinschaft', () => {
    it('beschreibt Fahrer und abgeholte Mitfahrer', () => {
        const zeilen = beschreibeFahrgemeinschaft({
            fahrten: [{fahrer: 'sr', mitfahrer: ['sra1', 'sra2'], km: 61, treffpunkt: null}],
            km: {sr: 61, sra1: 0, sra2: 0}, gesamt: 61, ersparnis: 40,
        }, 'sra2');

        expect(zeilen).toEqual([{text: 'SR fährt und holt SRA 1 und SRA 2 (du) ab (61 km)', treffpunkt: null}]);
    });

    it('nennt, wer allein faehrt', () => {
        expect(beschreibeFahrgemeinschaft({
            fahrten: [{fahrer: 'sr', mitfahrer: ['sra1'], km: 44, treffpunkt: null},
                {fahrer: 'sra2', mitfahrer: [], km: 50, treffpunkt: null}],
            km: {}, gesamt: 94, ersparnis: 6,
        }, null).map((z) => z.text)).toEqual(['SR fährt und holt SRA 1 ab (44 km)', 'SRA 2 fährt allein (50 km)']);
    });

    it('beschreibt einen Treffpunkt mit den eigenen Kilometern der Zubringer', () => {
        const treffpunkt = {lat: 50.8076, lon: 11.5856, name: 'Kahla'};
        const [zeile] = beschreibeFahrgemeinschaft({
            fahrten: [{fahrer: 'sr', mitfahrer: ['sra1', 'sra2'], km: 60, treffpunkt, zubringer: {sra1: 4, sra2: 12}}],
            km: {sr: 60, sra1: 4, sra2: 12}, gesamt: 76, ersparnis: 30,
        }, 'sra1');

        expect(zeile.text).toBe('SR fährt (60 km), SRA 1 (du) (4 km) und SRA 2 (12 km) kommen zum Treffpunkt etwa bei Kahla');
        expect(zeile.treffpunkt).toBe(treffpunkt);
    });

    it('sagt "unterwegs", wenn der Ort keinen Namen hat', () => {
        const [zeile] = beschreibeFahrgemeinschaft({
            fahrten: [{fahrer: 'sr', mitfahrer: ['sra1'], km: 60, treffpunkt: {lat: 50, lon: 11, name: null}, zubringer: {sra1: 4}}],
            km: {}, gesamt: 64, ersparnis: 3,
        }, null);
        expect(zeile.text).toBe('SR fährt (60 km), SRA 1 (4 km) kommt zum Treffpunkt unterwegs');
    });
});

describe('treffpunktLink', () => {
    it('points openstreetmap.org at the meeting point', () => {
        expect(treffpunktLink({lat: 50.80761, lon: 11.58561, name: null}))
            .toBe('https://www.openstreetmap.org/?mlat=50.8076&mlon=11.5856#map=13/50.8076/11.5856');
    });
});
