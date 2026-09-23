import {type RefObject, useEffect, useState} from 'react';

/**
 * Ob der Besucher in seinem System weniger Bewegung eingestellt hat.
 *
 * Jede Animation auf der Landingpage ist Dekoration - sie darf ausfallen,
 * ohne dass ein Inhalt verschwindet. Deshalb fragt jede der Hilfen hier
 * selbst nach, statt sich auf eine Medienabfrage im CSS zu verlassen: was
 * in JavaScript entsteht (Zahlenlauf, Parallaxe), erreicht das CSS nicht.
 */
export function magKeineBewegung(): boolean {
    return typeof window !== 'undefined'
        && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/**
 * Blendet alle Elemente mit `data-reveal` ein, sobald sie in den sichtbaren
 * Bereich scrollen - sie bekommen dann die Klasse `is-revealed`.
 *
 * Ein einziger Beobachter fuer die ganze Seite statt einer Ref je Element:
 * die Landingpage ist statisch, ihre Knoten stehen also schon beim ersten
 * Effekt fest. Nachtraeglich eingehaengte Elemente erfasst der Beobachter
 * nicht - auf dieser Seite gibt es keine.
 */
export function useRevealOnScroll(): void {
    useEffect(() => {
        const elemente = Array.from(document.querySelectorAll<HTMLElement>('[data-reveal]'));

        // Ohne Beobachter (oder ohne Wunsch nach Bewegung) ist sofort alles
        // sichtbar. Der Text darf nie an einer Animation haengen.
        if (magKeineBewegung() || !('IntersectionObserver' in window)) {
            elemente.forEach((element) => element.classList.add('is-revealed'));
            return;
        }

        const beobachter = new IntersectionObserver(
            (eintraege) => {
                eintraege.forEach((eintrag) => {
                    if (!eintrag.isIntersecting) {
                        return;
                    }
                    eintrag.target.classList.add('is-revealed');
                    // Einmal eingeblendet bleibt eingeblendet - beim
                    // Zurueckscrollen soll nichts wieder verschwinden.
                    beobachter.unobserve(eintrag.target);
                });
            },
            {rootMargin: '0px 0px -8% 0px', threshold: 0.15},
        );

        elemente.forEach((element) => beobachter.observe(element));
        return () => beobachter.disconnect();
    }, []);
}

/**
 * Ob ein Element gerade im Fenster steht.
 *
 * `rand` verschiebt die Grenze wie rootMargin beim IntersectionObserver,
 * z.B. '-56px 0px 0px 0px', damit eine feste Kopfzeile nicht mitzaehlt. Mit
 * `einmal` bleibt der Wert nach dem ersten Sichtbarwerden auf true stehen.
 * Ohne Beobachter im Browser gilt das Element als sichtbar - was davon
 * abhaengt, soll dann lieber einfach da sein.
 */
export function useImBild<T extends Element>(
    ref: RefObject<T | null>,
    {rand = '0px', einmal = false, anfang = true}: { rand?: string; einmal?: boolean; anfang?: boolean } = {},
): boolean {
    const [imBild, setImBild] = useState(anfang);

    useEffect(() => {
        const element = ref.current;
        if (!element || !('IntersectionObserver' in window)) {
            return;
        }

        const beobachter = new IntersectionObserver(
            ([eintrag]) => {
                setImBild(eintrag.isIntersecting);
                if (einmal && eintrag.isIntersecting) {
                    beobachter.disconnect();
                }
            },
            {rootMargin: rand},
        );

        beobachter.observe(element);
        return () => beobachter.disconnect();
    }, [ref, rand, einmal]);

    return imBild;
}

/**
 * Wie weit ein Bereich durch das Fenster gewandert ist, von 0 bis 1.
 *
 * 0, solange seine Oberkante noch im unteren Fuenftel steht, 1, sobald seine
 * Unterkante die obere Bildschirmhaelfte erreicht hat. Damit laesst sich eine
 * Linie oder ein Fortschritt an das Scrollen koppeln.
 */
export function useScrollProgress<T extends HTMLElement>(ref: RefObject<T | null>): number {
    // Ohne Bewegung gilt der Weg von vornherein als zurueckgelegt, sonst
    // bliebe eine Fortschrittslinie fuer immer leer.
    const [ruhig] = useState(magKeineBewegung);
    const [fortschritt, setFortschritt] = useState(ruhig ? 1 : 0);

    useEffect(() => {
        if (ruhig) {
            return;
        }

        let bild = 0;

        const messen = () => {
            bild = 0;
            const element = ref.current;
            if (!element) {
                return;
            }
            const kasten = element.getBoundingClientRect();
            const beginn = window.innerHeight * 0.85;
            const ende = window.innerHeight * 0.4;
            const strecke = kasten.height + beginn - ende;
            setFortschritt(Math.min(1, Math.max(0, (beginn - kasten.top) / strecke)));
        };

        // Beim Scrollen hoechstens einmal je Bild rechnen.
        const anstossen = () => {
            if (!bild) {
                bild = requestAnimationFrame(messen);
            }
        };

        messen();
        window.addEventListener('scroll', anstossen, {passive: true});
        window.addEventListener('resize', anstossen);
        return () => {
            if (bild) {
                cancelAnimationFrame(bild);
            }
            window.removeEventListener('scroll', anstossen);
            window.removeEventListener('resize', anstossen);
        };
    }, [ref, ruhig]);

    return fortschritt;
}

/**
 * Zaehlt von 0 auf `ziel` hoch, sobald ein Ziel vorliegt. Solange `ziel`
 * null ist (die Zahl also noch geladen wird), bleibt der Wert bei 0.
 */
export function useCountUp(ziel: number | null, dauer = 1400): number {
    const [ruhig] = useState(magKeineBewegung);
    const [wert, setWert] = useState(0);

    useEffect(() => {
        if (ziel === null || ruhig) {
            return;
        }

        let bild = 0;
        const beginn = performance.now();

        const schritt = (jetzt: number) => {
            const anteil = Math.min(1, (jetzt - beginn) / dauer);
            // Kubisch ausrollen, damit die Zahl am Ende weich stehen bleibt.
            setWert(Math.round(ziel * (1 - Math.pow(1 - anteil, 3))));
            if (anteil < 1) {
                bild = requestAnimationFrame(schritt);
            }
        };

        bild = requestAnimationFrame(schritt);
        return () => cancelAnimationFrame(bild);
    }, [ziel, dauer, ruhig]);

    // Ohne Bewegung steht die Zahl sofort auf ihrem Ziel.
    return ruhig ? (ziel ?? 0) : wert;
}
