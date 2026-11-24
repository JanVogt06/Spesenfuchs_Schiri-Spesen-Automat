import {describe, expect, it} from 'vitest';
import {beschreibeFahrgemeinschaft, rollenName} from './fahrten';

describe('rollenName', () => {
    it('markiert die eigene Rolle', () => {
        expect(rollenName('sra1', 'sra1')).toBe('SRA 1 (du)');
        expect(rollenName('sr', 'sra1')).toBe('SR');
        expect(rollenName('sra2', null)).toBe('SRA 2');
    });
});

describe('beschreibeFahrgemeinschaft', () => {
    it('beschreibt Fahrer, Mitfahrer und allein Fahrende', () => {
        const zeilen = beschreibeFahrgemeinschaft({
            fahrten: [
                {fahrer: 'sr', mitfahrer: ['sra1', 'sra2'], km: 61},
            ],
            km: {sr: 61, sra1: 0, sra2: 0}, gesamt: 61, ersparnis: 40,
        }, 'sra2');

        expect(zeilen).toEqual(['SR fährt und holt SRA 1 und SRA 2 (du) ab (61 km)']);
    });

    it('nennt, wer allein faehrt', () => {
        expect(beschreibeFahrgemeinschaft({
            fahrten: [{fahrer: 'sr', mitfahrer: ['sra1'], km: 44}, {fahrer: 'sra2', mitfahrer: [], km: 50}],
            km: {}, gesamt: 94, ersparnis: 6,
        }, null)).toEqual(['SR fährt und holt SRA 1 ab (44 km)', 'SRA 2 fährt allein (50 km)']);
    });
});
