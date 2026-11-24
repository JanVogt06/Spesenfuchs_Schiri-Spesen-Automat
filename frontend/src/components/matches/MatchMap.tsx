import {useEffect, useRef, useState} from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import {getMatchGeo, type GeoDaten, type GeoPunkt} from '@/lib/matches';
import {useTheme} from '@/components/ThemeProvider';
import {AlertCircle, Loader2, MapPin, RotateCw} from 'lucide-react';
import {Button} from '@/components/ui/button';

/**
 * Colors of the pins.
 *
 * Three colors for the three assigned officials, the venue on the other hand neutral and in
 * a different shape. This is not a matter of taste but a consequence of the
 * color-blindness check: four categorical colors that all appear on a
 * map at the same time and in any neighborhood no longer keep the
 * required distance - three do, in both themes. The
 * venue is not a fourth person anyway, but the destination, and therefore carries
 * its own shape instead of its own color.
 *
 * In addition, each pin contains its abbreviation: the assignment never depends
 * on color alone.
 */
const FARBEN = {
    light: {
        'SR': '#2a78d6',
        'SRA 1': '#eb6834',
        'SRA 2': '#1baf7a',
        spielstaette: '#1c1c1a',
        ring: '#ffffff',
    },
    dark: {
        'SR': '#3987e5',
        'SRA 1': '#d95926',
        'SRA 2': '#199e70',
        spielstaette: '#f5f5f0',
        ring: '#1a1a19',
    },
} as const;

const FALLBACK_FARBE = {light: '#4a3aa7', dark: '#9085e9'} as const;

function farbeFuer(rolle: string, modus: 'light' | 'dark'): string {
    const palette = FARBEN[modus];
    return palette[rolle as keyof typeof palette] ?? FALLBACK_FARBE[modus];
}

/** "SRA 1" -> "A1"; keeps the pin narrow enough to stay legible */
function kuerzel(rolle: string): string {
    const treffer = rolle.match(/^SRA\s*(\d+)$/i);
    if (treffer) return `A${treffer[1]}`;
    return rolle === 'SR' ? 'SR' : rolle.slice(0, 3);
}

function beschriftung(punkt: GeoPunkt): string {
    return punkt.eintraege.map(e => kuerzel(e.rolle)).join('·');
}

function escapeHtml(text: string): string {
    return text.replace(/[&<>"']/g, zeichen => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[zeichen] as string));
}

/**
 * Appearance of a pin - described once, used by the map and the legend.
 *
 * On the map the pin is HTML for Leaflet and in the legend it is JSX. Without
 * this shared source the two representations would sooner or later
 * drift apart, and then the legend would show a color that appears
 * nowhere on the map.
 */
function darstellung(punkt: GeoPunkt, modus: 'light' | 'dark') {
    const istSpielort = punkt.typ === 'spielstaette';
    const text = istSpielort ? '' : beschriftung(punkt);

    return {
        istSpielort,
        text,
        farbe: istSpielort
            ? FARBEN[modus].spielstaette
            : farbeFuer(punkt.eintraege[0].rolle, modus),
        ring: FARBEN[modus].ring,
        radius: istSpielort ? 8 : 14,
    };
}

/** The flag symbol of the venue (identical to lucide "flag") */
const FAHNE_PFAD = 'M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z';

/** Pin as HTML: circle with abbreviation for people, square with flag for the venue */
function icon(punkt: GeoPunkt, modus: 'light' | 'dark'): L.DivIcon {
    const {istSpielort, text, farbe, ring, radius} = darstellung(punkt, modus);

    // Imprecise points (only the center of a town) get a dashed
    // halo - otherwise a rough approximation would look like an exact address.
    const hof = punkt.genauigkeit === 'ort'
        ? `<span style="position:absolute;inset:-6px;border:2px dashed ${farbe};border-radius:${radius + 2}px;opacity:.55"></span>`
        : '';

    const inhalt = istSpielort
        ? `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="${ring}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="${FAHNE_PFAD}"/><line x1="4" y1="22" x2="4" y2="15"/></svg>`
        : `<span style="color:${ring};font-size:11px;font-weight:700;letter-spacing:.02em;line-height:1">${escapeHtml(text)}</span>`;

    const breite = Math.max(28, 16 + text.length * 7);

    return L.divIcon({
        className: 'spesen-pin',
        iconSize: [breite, 28],
        iconAnchor: [breite / 2, 14],
        popupAnchor: [0, -16],
        html: `<span style="position:relative;display:flex;align-items:center;justify-content:center;
                     width:${breite}px;height:28px;background:${farbe};
                     border:2px solid ${ring};border-radius:${radius}px;
                     box-shadow:0 1px 4px rgb(0 0 0 / .4);box-sizing:border-box">${hof}${inhalt}</span>`,
    });
}

/** The same pin, scaled down, for the legend */
function PinBadge({punkt, modus}: { punkt: GeoPunkt; modus: 'light' | 'dark' }) {
    const {istSpielort, text, farbe, ring, radius} = darstellung(punkt, modus);

    return (
        <span
            aria-hidden="true"
            className="inline-flex h-5 shrink-0 items-center justify-center px-1 text-[10px] font-bold"
            style={{
                minWidth: '20px',
                background: farbe,
                color: ring,
                border: `1.5px solid ${ring}`,
                borderRadius: `${radius}px`,
                boxShadow: '0 1px 2px rgb(0 0 0 / .25)',
            }}
        >
            {istSpielort ? (
                <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke={ring}
                     strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d={FAHNE_PFAD}/>
                    <line x1="4" y1="22" x2="4" y2="15"/>
                </svg>
            ) : text}
        </span>
    );
}

function popup(punkt: GeoPunkt): string {
    const zeilen = punkt.eintraege
        .map(e => `<strong>${escapeHtml(e.rolle)}</strong> · ${escapeHtml(e.name)}`)
        .join('<br>');
    const hinweis = punkt.genauigkeit === 'ort'
        ? '<div style="margin-top:4px;opacity:.7">Ungefähre Lage: nur der Ort war auffindbar.</div>'
        : '';
    return `<div style="font-size:12px;line-height:1.5">${zeilen}
            <div style="margin-top:2px;opacity:.75">${escapeHtml(punkt.adresse)}</div>${hinweis}</div>`;
}

interface MatchMapProps {
    matchId: number;
}

/**
 * Map with the addresses of the assigned officials and the venue.
 *
 * Only loaded when it is needed - the component sits in the
 * expanded area of a match card and is not rendered otherwise.
 */
export function MatchMap({matchId}: MatchMapProps) {
    const {resolvedTheme} = useTheme();
    const [versuch, setVersuch] = useState(0);

    // The result carries the key it belongs to. The loading state follows
    // from that instead of being tracked separately: a retry
    // inevitably shows the spinner again, and a response that belongs to
    // a superseded request can no longer be displayed.
    const schluessel = `${matchId}#${versuch}`;
    const [ergebnis, setErgebnis] = useState<
        { schluessel: string; daten: GeoDaten | null; fehler: string } | null
    >(null);

    const containerRef = useRef<HTMLDivElement>(null);

    const laedt = ergebnis?.schluessel !== schluessel;
    const daten = laedt ? null : ergebnis.daten;
    const fehler = laedt ? '' : ergebnis.fehler;

    useEffect(() => {
        let abgebrochen = false;

        getMatchGeo(matchId)
            .then(antwort => {
                if (!abgebrochen) setErgebnis({schluessel, daten: antwort, fehler: ''});
            })
            .catch(() => {
                if (!abgebrochen) {
                    setErgebnis({
                        schluessel,
                        daten: null,
                        fehler: 'Die Karte konnte nicht geladen werden.',
                    });
                }
            });

        return () => {
            abgebrochen = true;
        };
    }, [matchId, schluessel]);

    // Build the map as soon as points are available. A theme change rebuilds it -
    // the pins carry their colors fixed in the markup.
    useEffect(() => {
        const container = containerRef.current;
        if (!container || !daten || daten.punkte.length === 0) return;

        const map = L.map(container, {
            // The mouse wheel belongs to the page: otherwise the view would stay
            // stuck on the map while scrolling instead of moving on.
            scrollWheelZoom: false,
            attributionControl: true,
        });

        L.tileLayer(daten.kacheln.url, {
            attribution: daten.kacheln.attribution,
            maxZoom: 19,
        }).addTo(map);

        for (const punkt of daten.punkte) {
            L.marker([punkt.lat, punkt.lon], {
                icon: icon(punkt, resolvedTheme),
                title: punkt.eintraege.map(e => `${e.rolle}: ${e.name}`).join(' · '),
            })
                .addTo(map)
                .bindPopup(popup(punkt));
        }

        // Everything in view: that is exactly the purpose of the map. maxZoom caps
        // the case where all addresses are close together - without
        // it a single point would be shown at the highest zoom level.
        //
        // The padding is more generous than it looks like it needs to be: fitBounds only knows
        // the coordinates, not the pins sitting on top of them. A pin with
        // two abbreviations extends a good 25 pixels to each side, plus the halo for
        // imprecise locations - without this margin it would stick to the edge.
        map.fitBounds(
            L.latLngBounds(daten.punkte.map(p => [p.lat, p.lon] as [number, number])),
            {padding: [40, 40], maxZoom: 14},
        );

        // The map is created in an area that has only just been expanded.
        // Without this follow-up call Leaflet does not yet know the final size
        // and loads tiles for a field that is too small.
        const nachmessen = requestAnimationFrame(() => map.invalidateSize());

        return () => {
            cancelAnimationFrame(nachmessen);
            map.remove();
        };
    }, [daten, resolvedTheme]);

    const rahmen = 'rounded-lg border border-dashed';

    if (laedt) {
        return (
            <div className={`${rahmen} flex h-64 items-center justify-center gap-2 text-sm text-muted-foreground`}>
                <Loader2 className="size-4 animate-spin"/>
                Karte wird geladen...
            </div>
        );
    }

    if (fehler) {
        return (
            <div className={`${rahmen} flex h-32 flex-col items-center justify-center gap-2 px-3 text-center text-sm text-muted-foreground`}>
                <span className="flex items-center gap-1.5">
                    <AlertCircle className="size-4 shrink-0"/>
                    {fehler}
                </span>
                <Button size="sm" variant="outline" onClick={() => setVersuch(v => v + 1)}>
                    <RotateCw className="size-3.5"/>
                    Erneut versuchen
                </Button>
            </div>
        );
    }

    if (!daten || daten.punkte.length === 0) {
        return (
            <div className={`${rahmen} flex h-32 flex-col items-center justify-center gap-2 px-3 text-center text-sm text-muted-foreground`}>
                <span className="flex items-center gap-1.5">
                    <MapPin className="size-4 shrink-0"/>
                    {daten?.gestoert
                        ? 'Der Adressdienst ist gerade nicht erreichbar.'
                        : 'Zu diesem Spiel ließ sich keine Anschrift auf der Karte verorten.'}
                </span>
                {daten?.gestoert && (
                    <Button size="sm" variant="outline" onClick={() => setVersuch(v => v + 1)}>
                        <RotateCw className="size-3.5"/>
                        Erneut versuchen
                    </Button>
                )}
            </div>
        );
    }

    return (
        <div className="space-y-2">
            {/*
              isolate: Leaflet assigns z-index values up to 800 internally. Without its own
              stacking context the map would slide over the header of the application
              while scrolling.
            */}
            <div
                ref={containerRef}
                className={`${rahmen} isolate h-64 w-full overflow-hidden sm:h-80`}
            />

            {/*
              Legend - one line per pin, not per person. If two assigned officials share an address,
              there is only one pin on the map; one line per person would list this pin twice
              and the second time show a color that is not there at all.
              This way the legend reads as what it is: the map in text form.
              So liest sich die Legende als das, was sie ist: die Karte in Text.
            */}
            <ul className="grid gap-1.5 text-xs sm:grid-cols-2">
                {daten.punkte.map(punkt => (
                    <li key={`${punkt.lat},${punkt.lon}`} className="flex items-start gap-2">
                        <PinBadge punkt={punkt} modus={resolvedTheme}/>
                        <span className="min-w-0 break-words pt-0.5">
                            {punkt.eintraege.map((eintrag, idx) => (
                                <span key={eintrag.rolle}>
                                    {idx > 0 && ', '}
                                    <span className="text-muted-foreground">{eintrag.rolle}</span>{' '}
                                    {eintrag.name}
                                </span>
                            ))}
                            {punkt.genauigkeit === 'ort' && (
                                <span className="text-muted-foreground"> · nur Ort, ungefähre Lage</span>
                            )}
                        </span>
                    </li>
                ))}
            </ul>

            {daten.ohne_treffer.length > 0 && (
                <p className="text-xs text-muted-foreground">
                    Ohne Position auf der Karte:{' '}
                    {daten.ohne_treffer.map(e => `${e.rolle} (${e.name})`).join(', ')}
                    {daten.gestoert
                        ? ' – der Adressdienst war nicht erreichbar.'
                        : ' – die Anschrift war nicht auffindbar.'}
                </p>
            )}
        </div>
    );
}
