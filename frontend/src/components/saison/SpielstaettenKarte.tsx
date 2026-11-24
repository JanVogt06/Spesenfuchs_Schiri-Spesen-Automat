import {useEffect, useMemo, useRef, useState} from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import {Card, CardContent, CardHeader, CardTitle} from '@/components/ui/card';
import {Separator} from '@/components/ui/separator';
import {useTheme} from '@/components/ThemeProvider';
import {getSpielstaetten, inSaison, ortPopup, type Spielstaetten} from '@/lib/spielstaetten';
import {cn} from '@/lib/utils';
import {Loader2, MapPinned} from 'lucide-react';

const MAX_NACHFRAGEN = 20;
const NACHFRAGE_MS = 1500;

// Same color as the expenses in the statistics, checked against both surfaces
const FARBE = {light: {fuellung: '#2e7d4f', ring: '#ffffff'}, dark: {fuellung: '#3fa86e', ring: '#1a1a19'}} as const;

interface SpielstaettenKarteProps {
    /** The season selected in the tab - the switcher can narrow down to it */
    saison: string | null;
}

/**
 * Map of all venues where one has already officiated - across all
 * read seasons or just the selected one. Future matches never appear on it.
 */
export function SpielstaettenKarte({saison}: SpielstaettenKarteProps) {
    const {resolvedTheme} = useTheme();
    const [daten, setDaten] = useState<Spielstaetten | null>(null);
    const [fehler, setFehler] = useState(false);
    const [nurSaison, setNurSaison] = useState(false);
    const containerRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        let aktiv = true;
        let timer: ReturnType<typeof setTimeout> | undefined;
        let versuche = 0;
        let ohneFortschritt = 0;
        let vorherOffen = Infinity;

        // The server only looks up new venues for a few seconds per call
        const laden = () => {
            getSpielstaetten()
                .then((antwort) => {
                    if (!aktiv) return;
                    setDaten(antwort);
                    versuche += 1;
                    ohneFortschritt = antwort.offen < vorherOffen ? 0 : ohneFortschritt + 1;
                    vorherOffen = antwort.offen;
                    if (antwort.offen > 0 && versuche < MAX_NACHFRAGEN && ohneFortschritt < 3) {
                        timer = setTimeout(laden, NACHFRAGE_MS);
                    }
                })
                .catch(() => aktiv && setFehler(true));
        };
        laden();

        return () => {
            aktiv = false;
            if (timer) clearTimeout(timer);
        };
    }, []);

    const orte = useMemo(
        () => (daten ? inSaison(daten.orte, nurSaison ? saison : null) : []),
        [daten, nurSaison, saison],
    );
    const einsaetze = orte.reduce((summe, ort) => summe + ort.anzahl, 0);

    useEffect(() => {
        const container = containerRef.current;
        if (!container || !daten || orte.length === 0) return;

        const map = L.map(container, {scrollWheelZoom: false, attributionControl: true});
        L.tileLayer(daten.kacheln.url, {attribution: daten.kacheln.attribution, maxZoom: 19}).addTo(map);

        const farbe = FARBE[resolvedTheme];
        // Draw frequently visited venues last so they lie on top
        for (const ort of [...orte].reverse()) {
            L.circleMarker([ort.lat, ort.lon], {
                radius: 5 + Math.min(9, Math.sqrt(ort.anzahl) * 2),
                color: farbe.ring,
                weight: 2,
                fillColor: farbe.fuellung,
                fillOpacity: 0.85,
                dashArray: ort.genauigkeit === 'ort' ? '3 3' : undefined,
            })
                .addTo(map)
                .bindTooltip(`${ort.name} · ${ort.anzahl} ${ort.anzahl === 1 ? 'Einsatz' : 'Einsätze'}`)
                .bindPopup(ortPopup(ort));
        }

        map.fitBounds(L.latLngBounds(orte.map((o) => [o.lat, o.lon] as [number, number])),
            {padding: [30, 30], maxZoom: 13});
        const nachmessen = requestAnimationFrame(() => map.invalidateSize());
        return () => {
            cancelAnimationFrame(nachmessen);
            map.remove();
        };
    }, [daten, orte, resolvedTheme]);

    const umschalter = saison && (
        <div role="group" aria-label="Zeitraum der Karte" className="inline-flex rounded-lg border bg-card p-0.5">
            {[{wert: false, label: 'Alle Saisons'}, {wert: true, label: `Saison ${saison}`}].map((eintrag) => (
                <button
                    key={eintrag.label}
                    type="button"
                    aria-pressed={nurSaison === eintrag.wert}
                    onClick={() => setNurSaison(eintrag.wert)}
                    className={cn(
                        'rounded-md px-2.5 py-1 text-xs font-medium transition-colors',
                        nurSaison === eintrag.wert ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:text-foreground'
                    )}
                >
                    {eintrag.label}
                </button>
            ))}
        </div>
    );

    let inhalt;
    if (fehler) {
        inhalt = <p className="text-sm text-muted-foreground">Die Karte konnte nicht geladen werden.</p>;
    } else if (!daten) {
        inhalt = (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin"/>
                Suche die Plätze…
            </p>
        );
    } else {
        inhalt = (
            <div className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm">
                        <span className="font-semibold tabular-nums">{orte.length}</span>{' '}
                        {orte.length === 1 ? 'Spielstätte' : 'Spielstätten'}
                        <span className="text-muted-foreground"> · {einsaetze} {einsaetze === 1 ? 'Einsatz' : 'Einsätze'}</span>
                    </p>
                    {umschalter}
                </div>

                {orte.length === 0 ? (
                    <p className="rounded-lg border border-dashed px-3 py-8 text-center text-sm text-muted-foreground">
                        {daten.offen > 0
                            ? 'Die Plätze werden gerade gesucht…'
                            : 'Noch kein vergangenes Spiel mit bekannter Spielstätte.'}
                    </p>
                ) : (
                    // isolate: Leaflet assigns z-index up to 800 - otherwise the map would lie above the header
                    <div ref={containerRef} className="isolate h-72 w-full overflow-hidden rounded-lg border sm:h-96"/>
                )}

                <div className="space-y-1 text-xs text-muted-foreground">
                    <p>Nur Plätze vergangener eigener Einsätze – aus den Ansetzungen und den Spielberichten.</p>
                    {daten.offen > 0 && (
                        <p className="flex items-center gap-1.5">
                            <Loader2 className="size-3 animate-spin"/>
                            Noch {daten.offen} {daten.offen === 1 ? 'Platz wird' : 'Plätze werden'} gesucht…
                        </p>
                    )}
                    {daten.ohne_treffer > 0 && (
                        <p>Ohne Position: {daten.ohne_treffer} {daten.ohne_treffer === 1 ? 'Platz, dessen Adresse' : 'Plätze, deren Adresse'} nicht auffindbar war.</p>
                    )}
                </div>
            </div>
        );
    }

    return (
        <Card className="gap-0 overflow-hidden py-0">
            <CardHeader className="flex h-11 flex-row items-center gap-2 px-4 py-0 sm:px-6">
                <MapPinned className="size-4 text-muted-foreground"/>
                <CardTitle className="text-sm">Besuchte Spielstätten</CardTitle>
            </CardHeader>
            <Separator/>
            <CardContent className="p-4 sm:p-6">{inhalt}</CardContent>
        </Card>
    );
}
