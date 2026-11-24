import {type RefObject, useEffect, useState} from 'react';

/**
 * Whether the visitor has set reduced motion in their system.
 *
 * Every animation on the landing page is decoration - it may be dropped
 * without any content disappearing. That is why each of the helpers here asks
 * for itself instead of relying on a media query in the CSS: what
 * arises in JavaScript (number count-up, parallax) is not reached by the CSS.
 */
export function magKeineBewegung(): boolean {
    return typeof window !== 'undefined'
        && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/**
 * Reveals all elements with `data-reveal` as soon as they scroll into the visible
 * area - they then get the class `is-revealed`.
 *
 * A single observer for the whole page instead of one ref per element:
 * the landing page is static, so its nodes are already fixed at the first
 * effect. The observer does not pick up elements attached later
 * - there are none on this page.
 */
export function useRevealOnScroll(): void {
    useEffect(() => {
        const elemente = Array.from(document.querySelectorAll<HTMLElement>('[data-reveal]'));

        // Without an observer (or without a wish for motion) everything is immediately
        // visible. The text must never depend on an animation.
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
                    // Once revealed stays revealed - when
                    // scrolling back nothing should disappear again.
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
 * Whether an element is currently in the window.
 *
 * `rand` shifts the boundary like rootMargin on the IntersectionObserver,
 * e.g. '-56px 0px 0px 0px', so that a fixed header does not count. With
 * `einmal` the value stays true after first becoming visible.
 * Without an observer in the browser the element counts as visible - whatever
 * depends on it should rather simply be there.
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
 * How far a section has travelled through the window, from 0 to 1.
 *
 * 0 as long as its top edge is still in the lower fifth, 1 as soon as its
 * bottom edge has reached the upper half of the screen. This allows a
 * line or a progress indicator to be coupled to scrolling.
 */
export function useScrollProgress<T extends HTMLElement>(ref: RefObject<T | null>): number {
    // Without motion the path counts as covered from the start, otherwise
    // a progress line would stay empty forever.
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

        // While scrolling compute at most once per frame.
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
 * Counts up from 0 to `ziel` as soon as a target is available. As long as `ziel`
 * is null (i.e. the number is still loading), the value stays at 0.
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
            // Ease out cubically so that the number comes to rest softly at the end.
            setWert(Math.round(ziel * (1 - Math.pow(1 - anteil, 3))));
            if (anteil < 1) {
                bild = requestAnimationFrame(schritt);
            }
        };

        bild = requestAnimationFrame(schritt);
        return () => cancelAnimationFrame(bild);
    }, [ziel, dauer, ruhig]);

    // Without motion the number immediately stands at its target.
    return ruhig ? (ziel ?? 0) : wert;
}
