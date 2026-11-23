import {describe, expect, it} from 'vitest';
import {cn} from './utils';

describe('cn', () => {
    it('verbindet Klassen und laesst Falsches weg', () => {
        expect(cn('a', false, null, undefined, 'b', {c: true, d: false}, ['e'])).toBe('a b c e');
    });

    it('loest Tailwind-Konflikte zugunsten der letzten Klasse', () => {
        expect(cn('px-2 py-1', 'px-4')).toBe('py-1 px-4');
        expect(cn('text-muted-foreground', 'text-primary')).toBe('text-primary');
    });

    it('liefert ohne Eingabe einen leeren String', () => {
        expect(cn()).toBe('');
    });
});
