import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {act, render, renderHook, screen} from '@testing-library/react';
import {useRef} from 'react';
import {magKeineBewegung, useCountUp, useImBild, useRevealOnScroll, useScrollProgress} from './useReveal';

/** Ein IntersectionObserver, den der Test von Hand ausloest */
class BeobachterAttrappe {
    static alle: BeobachterAttrappe[] = [];
    beobachtet = new Set<Element>();
    getrennt = false;
    rueckruf: (eintraege: {target: Element; isIntersecting: boolean}[]) => void;
    optionen: {rootMargin?: string; threshold?: number};
    constructor(
        rueckruf: (eintraege: {target: Element; isIntersecting: boolean}[]) => void,
        optionen: {rootMargin?: string; threshold?: number} = {},
    ) {
        this.rueckruf = rueckruf;
        this.optionen = optionen;
        BeobachterAttrappe.alle.push(this);
    }
    observe(element: Element) {
        this.beobachtet.add(element);
    }
    unobserve(element: Element) {
        this.beobachtet.delete(element);
    }
    disconnect() {
        this.getrennt = true;
        this.beobachtet.clear();
    }
    melde(element: Element, isIntersecting: boolean) {
        act(() => this.rueckruf([{target: element, isIntersecting}]));
    }
}

let wenigerBewegung = false;

beforeEach(() => {
    wenigerBewegung = false;
    BeobachterAttrappe.alle = [];
    vi.stubGlobal('matchMedia', vi.fn((query: string) => ({
        matches: query === '(prefers-reduced-motion: reduce)' && wenigerBewegung,
        media: query,
    })));
    vi.stubGlobal('IntersectionObserver', BeobachterAttrappe);
});

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('magKeineBewegung', () => {
    it('folgt prefers-reduced-motion', () => {
        expect(magKeineBewegung()).toBe(false);
        wenigerBewegung = true;
        expect(magKeineBewegung()).toBe(true);
    });
});

describe('useRevealOnScroll', () => {
    function Seite() {
        useRevealOnScroll();
        return (
            <div>
                <p data-reveal="" data-testid="eins">Eins</p>
                <p data-reveal="" data-testid="zwei">Zwei</p>
                <p data-testid="ohne">Ohne</p>
            </div>
        );
    }

    it('blendet ein Element ein, sobald es sichtbar wird, und beobachtet es dann nicht mehr', () => {
        render(<Seite/>);
        const [beobachter] = BeobachterAttrappe.alle;
        const eins = screen.getByTestId('eins');
        const zwei = screen.getByTestId('zwei');

        expect(BeobachterAttrappe.alle).toHaveLength(1);
        expect([...beobachter.beobachtet]).toEqual([eins, zwei]);
        expect(beobachter.optionen).toEqual({rootMargin: '0px 0px -8% 0px', threshold: 0.15});
        expect(eins).not.toHaveClass('is-revealed');

        beobachter.melde(eins, false);
        expect(eins).not.toHaveClass('is-revealed');

        beobachter.melde(eins, true);
        expect(eins).toHaveClass('is-revealed');
        expect(zwei).not.toHaveClass('is-revealed');
        expect(beobachter.beobachtet.has(eins)).toBe(false);
        expect(screen.getByTestId('ohne')).not.toHaveClass('is-revealed');
    });

    it('trennt den Beobachter beim Abbau', () => {
        const {unmount} = render(<Seite/>);
        unmount();
        expect(BeobachterAttrappe.alle[0].getrennt).toBe(true);
    });

    it('zeigt bei weniger Bewegung sofort alles', () => {
        wenigerBewegung = true;
        render(<Seite/>);

        expect(screen.getByTestId('eins')).toHaveClass('is-revealed');
        expect(screen.getByTestId('zwei')).toHaveClass('is-revealed');
        expect(BeobachterAttrappe.alle).toHaveLength(0);
    });

    it('zeigt ohne IntersectionObserver sofort alles', () => {
        delete (window as unknown as Record<string, unknown>).IntersectionObserver;
        render(<Seite/>);

        expect(screen.getByTestId('eins')).toHaveClass('is-revealed');
        expect(screen.getByTestId('zwei')).toHaveClass('is-revealed');
    });
});

describe('useImBild', () => {
    function Bereich({einmal, anfang, rand}: {einmal?: boolean; anfang?: boolean; rand?: string}) {
        const ref = useRef<HTMLDivElement>(null);
        const imBild = useImBild(ref, {einmal, anfang, rand});
        return <div ref={ref} data-testid="bereich">{imBild ? 'sichtbar' : 'verdeckt'}</div>;
    }

    it('folgt dem Beobachter in beide Richtungen', () => {
        render(<Bereich rand="-56px 0px 0px 0px"/>);
        const [beobachter] = BeobachterAttrappe.alle;
        const bereich = screen.getByTestId('bereich');

        expect(beobachter.optionen).toEqual({rootMargin: '-56px 0px 0px 0px'});
        expect(bereich).toHaveTextContent('sichtbar');
        beobachter.melde(bereich, false);
        expect(bereich).toHaveTextContent('verdeckt');
        beobachter.melde(bereich, true);
        expect(bereich).toHaveTextContent('sichtbar');
        expect(beobachter.getrennt).toBe(false);
    });

    it('beginnt mit dem Anfangswert', () => {
        render(<Bereich anfang={false}/>);
        expect(screen.getByTestId('bereich')).toHaveTextContent('verdeckt');
        expect(BeobachterAttrappe.alle[0].optionen).toEqual({rootMargin: '0px'});
    });

    it('trennt sich mit "einmal" nach dem ersten Sichtbarwerden', () => {
        render(<Bereich einmal anfang={false}/>);
        const [beobachter] = BeobachterAttrappe.alle;
        const bereich = screen.getByTestId('bereich');

        beobachter.melde(bereich, false);
        expect(beobachter.getrennt).toBe(false);
        beobachter.melde(bereich, true);
        expect(beobachter.getrennt).toBe(true);
        expect(bereich).toHaveTextContent('sichtbar');
    });

    it('gilt ohne IntersectionObserver als sichtbar', () => {
        delete (window as unknown as Record<string, unknown>).IntersectionObserver;
        render(<Bereich/>);
        expect(screen.getByTestId('bereich')).toHaveTextContent('sichtbar');
    });
});

describe('useScrollProgress', () => {
    let oben = 0;
    let bilder: FrameRequestCallback[] = [];

    function Strecke() {
        const ref = useRef<HTMLDivElement>(null);
        const fortschritt = useScrollProgress(ref);
        return <div ref={ref} data-testid="strecke">{fortschritt.toFixed(2)}</div>;
    }

    beforeEach(() => {
        oben = 0;
        bilder = [];
        vi.stubGlobal('innerHeight', 1000);
        vi.stubGlobal('requestAnimationFrame', vi.fn((cb: FrameRequestCallback) => bilder.push(cb)));
        vi.stubGlobal('cancelAnimationFrame', vi.fn());
        vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(
            () => ({top: oben, height: 550, bottom: oben + 550, left: 0, right: 0, width: 0, x: 0, y: oben}) as DOMRect,
        );
    });

    function scrolleAuf(top: number) {
        oben = top;
        window.dispatchEvent(new Event('scroll'));
        act(() => {
            const anstehend = bilder;
            bilder = [];
            anstehend.forEach((cb) => cb(0));
        });
    }

    it('laeuft von 0 (Oberkante unten) bis 1 (Unterkante in der oberen Haelfte)', () => {
        // Strecke = Hoehe 550 + 850 (Beginn) - 400 (Ende) = 1000
        oben = 900;
        render(<Strecke/>);
        const strecke = screen.getByTestId('strecke');
        expect(strecke).toHaveTextContent('0.00');

        scrolleAuf(850);
        expect(strecke).toHaveTextContent('0.00');
        scrolleAuf(350);
        expect(strecke).toHaveTextContent('0.50');
        scrolleAuf(-150);
        expect(strecke).toHaveTextContent('1.00');
        scrolleAuf(-2000);
        expect(strecke).toHaveTextContent('1.00');
    });

    it('rechnet hoechstens einmal je Bild', () => {
        render(<Strecke/>);
        window.dispatchEvent(new Event('scroll'));
        window.dispatchEvent(new Event('scroll'));
        window.dispatchEvent(new Event('resize'));
        expect(bilder).toHaveLength(1);
    });

    it('meldet sich beim Abbau ab und bricht ein offenes Bild ab', () => {
        const {unmount} = render(<Strecke/>);
        window.dispatchEvent(new Event('scroll'));
        unmount();

        expect(cancelAnimationFrame).toHaveBeenCalled();
        bilder = [];
        window.dispatchEvent(new Event('scroll'));
        expect(bilder).toHaveLength(0);
    });

    it('steht bei weniger Bewegung sofort auf 1', () => {
        wenigerBewegung = true;
        oben = 900;
        render(<Strecke/>);
        expect(screen.getByTestId('strecke')).toHaveTextContent('1.00');
    });
});

describe('useCountUp', () => {
    let bilder: FrameRequestCallback[] = [];

    beforeEach(() => {
        bilder = [];
        vi.spyOn(performance, 'now').mockReturnValue(0);
        vi.stubGlobal('requestAnimationFrame', vi.fn((cb: FrameRequestCallback) => bilder.push(cb)));
        vi.stubGlobal('cancelAnimationFrame', vi.fn());
    });

    function bild(zeit: number) {
        act(() => {
            const anstehend = bilder;
            bilder = [];
            anstehend.forEach((cb) => cb(zeit));
        });
    }

    it('bleibt bei 0, solange kein Ziel vorliegt', () => {
        const {result} = renderHook(() => useCountUp(null));
        expect(result.current).toBe(0);
        expect(requestAnimationFrame).not.toHaveBeenCalled();
    });

    it('zaehlt kubisch ausrollend bis zum Ziel und hoert dann auf', () => {
        const {result} = renderHook(() => useCountUp(1000, 1000));

        bild(0);
        expect(result.current).toBe(0);
        bild(500);
        // 1 - (1 - 0,5)^3 = 0,875
        expect(result.current).toBe(875);
        bild(1000);
        expect(result.current).toBe(1000);
        expect(bilder).toHaveLength(0);
    });

    it('bricht die Animation beim Abbau ab', () => {
        const {unmount} = renderHook(() => useCountUp(50));
        unmount();
        expect(cancelAnimationFrame).toHaveBeenCalled();
    });

    it('steht bei weniger Bewegung sofort auf dem Ziel', () => {
        wenigerBewegung = true;
        const {result, rerender} = renderHook(({ziel}) => useCountUp(ziel), {initialProps: {ziel: null as number | null}});
        expect(result.current).toBe(0);

        rerender({ziel: 42});
        expect(result.current).toBe(42);
        expect(requestAnimationFrame).not.toHaveBeenCalled();
    });
});
