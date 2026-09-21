import {useEffect, useRef, useState} from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import {getMatchGeo, type GeoDaten, type GeoPunkt} from '@/lib/matches';
import {useTheme} from '@/components/ThemeProvider';
import {AlertCircle, Loader2, MapPin, RotateCw} from 'lucide-react';
import {Button} from '@/components/ui/button';

/**
 * Farben der Pins.
 *
 * Drei Farben für die drei Angesetzten, der Spielort dagegen neutral und in
 * anderer Form. Das ist kein Geschmack, sondern eine Konsequenz aus der
 * Prüfung auf Farbfehlsichtigkeit: vier kategoriale Farben, die auf einer
 * Karte alle gleichzeitig und in beliebiger Nachbarschaft liegen, halten den
 * nötigen Abstand nicht mehr ein - drei tun es in beiden Themes. Der
 * Spielort ist ohnehin keine vierte Person, sondern das Ziel, und trägt
 * deshalb eine eigene Form statt einer eigenen Farbe.
 *
 * Zusätzlich steht in jedem Pin sein Kürzel: die Zuordnung hängt damit nie
 * allein an der Farbe.
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

/** "SRA 1" -> "A1"; hält den Pin schmal genug, um lesbar zu bleiben */
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
 * Aussehen eines Pins - einmal beschrieben, von Karte und Legende benutzt.
 *
 * Der Pin ist auf der Karte HTML für Leaflet und in der Legende JSX. Ohne
 * diese gemeinsame Quelle liefen die beiden Darstellungen früher oder später
 * auseinander, und dann zeigte die Legende eine Farbe, die auf der Karte
 * nirgends steht.
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

/** Das Fahnen-Symbol des Spielorts (identisch mit lucide "flag") */
const FAHNE_PFAD = 'M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z';

/** Pin als HTML: Kreis mit Kürzel für Personen, Quadrat mit Fahne für den Spielort */
function icon(punkt: GeoPunkt, modus: 'light' | 'dark'): L.DivIcon {
    const {istSpielort, text, farbe, ring, radius} = darstellung(punkt, modus);

    // Ungenaue Punkte (nur Ortsmittelpunkt) bekommen einen gestrichelten
    // Hof - sonst sähe eine grobe Näherung aus wie eine exakte Anschrift.
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

/** Derselbe Pin, verkleinert, für die Legende */
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
 * Karte mit den Anschriften der Angesetzten und dem Spielort.
 *
 * Wird erst geladen, wenn sie gebraucht wird - die Komponente hängt im
 * aufgeklappten Bereich einer Spielkarte und wird sonst nicht gerendert.
 */
export function MatchMap({matchId}: MatchMapProps) {
    const {resolvedTheme} = useTheme();
    const [versuch, setVersuch] = useState(0);

    // Das Ergebnis trägt den Schlüssel, zu dem es gehört. Daraus ergibt sich
    // der Ladezustand, statt ihn getrennt zu führen: ein erneuter Versuch
    // zeigt damit zwangsläufig wieder den Spinner, und eine Antwort, die zu
    // einer überholten Anfrage gehört, kann nicht mehr angezeigt werden.
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

    // Karte aufbauen, sobald Punkte da sind. Theme-Wechsel baut sie neu auf -
    // die Pins tragen ihre Farben fest im Markup.
    useEffect(() => {
        const container = containerRef.current;
        if (!container || !daten || daten.punkte.length === 0) return;

        const map = L.map(container, {
            // Das Mausrad gehört der Seite: sonst bliebe der Blick beim
            // Scrollen an der Karte hängen, statt weiterzulaufen.
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

        // Alles im Bild: genau das ist der Zweck der Karte. maxZoom deckelt
        // den Fall, dass alle Anschriften dicht beieinander liegen - ohne
        // das stünde man bei einem einzigen Punkt auf der höchsten Stufe.
        //
        // Der Rand ist großzügiger, als er aussehen muss: fitBounds kennt nur
        // die Koordinaten, nicht die Pins, die darüber sitzen. Ein Pin mit
        // zwei Kürzeln ragt gut 25 Pixel nach jeder Seite, dazu der Hof bei
        // ungenauer Lage - ohne diesen Abstand klebte er am Rand.
        map.fitBounds(
            L.latLngBounds(daten.punkte.map(p => [p.lat, p.lon] as [number, number])),
            {padding: [40, 40], maxZoom: 14},
        );

        // Die Karte entsteht in einem gerade erst aufgeklappten Bereich.
        // Ohne diesen Nachschlag kennt Leaflet die endgültige Größe noch
        // nicht und lädt Kacheln für ein zu kleines Feld.
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
              isolate: Leaflet vergibt intern z-index bis 800. Ohne eigenen
              Stapelkontext schöbe sich die Karte beim Scrollen über die
              Kopfzeile der Anwendung.
            */}
            <div
                ref={containerRef}
                className={`${rahmen} isolate h-64 w-full overflow-hidden sm:h-80`}
            />

            {/*
              Legende - eine Zeile je Pin, nicht je Person. Teilen sich zwei
              Angesetzte eine Anschrift, gibt es auf der Karte auch nur einen
              Pin; eine Zeile je Person würde diesen Pin zweimal auflisten und
              beim zweiten Mal eine Farbe zeigen, die dort gar nicht steht.
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
