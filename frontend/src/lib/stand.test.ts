import {describe, expect, it} from 'vitest';
import {formatStand, letzterStand} from './stand';

const JETZT = new Date(2026, 10, 24, 16, 30);

describe('letzterStand', () => {
    it('nimmt das Ende eines abgeschlossenen Abrufs', () => {
        const stand = letzterStand({status: 'completed', finished_at: '2026-11-24T02:00:00+00:00', progress: null});
        expect(stand?.toISOString()).toBe('2026-11-24T02:00:00.000Z');
    });

    it.each([
        ['laufend', {status: 'scraping', finished_at: null, progress: null}],
        ['fehlgeschlagen', {status: 'failed', finished_at: '2026-11-24T02:00:00+00:00', progress: null}],
        ['ohne Zeitstempel', {status: 'completed', finished_at: null, progress: null}],
        ['unbrauchbarer Zeitstempel', {status: 'completed', finished_at: 'gestern', progress: null}],
    ] as const)('hat keinen Stand: %s', (_, run) => {
        expect(letzterStand(run)).toBeNull();
    });

    it('hat ohne Abruf keinen Stand', () => {
        expect(letzterStand(null)).toBeNull();
        expect(letzterStand({status: 'idle', progress: null})).toBeNull();
    });
});

describe('formatStand', () => {
    it('sagt "heute" und "gestern"', () => {
        expect(formatStand(new Date(2026, 10, 24, 3, 0), JETZT)).toBe('heute, 03:00');
        expect(formatStand(new Date(2026, 10, 23, 3, 5), JETZT)).toBe('gestern, 03:05');
    });

    it('nennt aeltere Tage mit Datum, das Jahr nur ausserhalb des laufenden', () => {
        expect(formatStand(new Date(2026, 10, 22, 3, 0), JETZT)).toBe('22.11., 03:00');
        expect(formatStand(new Date(2025, 11, 31, 23, 59), JETZT)).toBe('31.12.2025, 23:59');
    });

    it('erkennt "gestern" auch ueber den Monatswechsel', () => {
        expect(formatStand(new Date(2026, 10, 30, 3, 0), new Date(2026, 11, 1, 9, 0))).toBe('gestern, 03:00');
    });
});
