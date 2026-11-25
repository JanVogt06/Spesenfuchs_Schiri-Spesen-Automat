import {useEffect, useRef, useState} from 'react';
import {Card, CardContent, CardHeader, CardTitle} from '@/components/ui/card';
import {Separator} from '@/components/ui/separator';
import {getStatistik, monatsName, type Statistik, type StatistikMonat} from '@/lib/statistik';
import {formatEuro} from '@/lib/spielberichte';
import {Euro, Loader2} from 'lucide-react';

// How often to poll at most while routes are outstanding
const MAX_NACHFRAGEN = 20;
const NACHFRAGE_MS = 1500;

/** Hatching for estimated travel costs - same color, but recognizably "uncertain" */
const SCHRAFFUR = 'repeating-linear-gradient(45deg, var(--diagramm-fahrt) 0 2px, transparent 2px 5px)';

interface SpesenStatistikProps {
    /** null: the newest season with matches. Remount (key) on a change of season, then the state starts fresh */
    saison: string | null;
    /** Called with every answer - the page builds its season selection from it */
    onGeladen?: (statistik: Statistik) => void;
}

function Kennzahl({label, wert, zusatz}: {label: string; wert: string; zusatz?: string}) {
    return (
        <div className="min-w-0">
            <p className="text-xs text-muted-foreground">{label}</p>
            <p className="mt-0.5 text-xl font-semibold tabular-nums">{wert}</p>
            {zusatz && <p className="text-xs text-muted-foreground">{zusatz}</p>}
        </div>
    );
}

function Legende() {
    const eintraege = [
        {name: 'Spesen', stil: {background: 'var(--diagramm-spesen)'}},
        {name: 'Fahrtkosten', stil: {background: 'var(--diagramm-fahrt)'}},
        {name: 'Fahrtkosten geschätzt', stil: {background: SCHRAFFUR, boxShadow: 'inset 0 0 0 1px var(--diagramm-fahrt)'}},
    ];
    return (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            {eintraege.map((eintrag) => (
                <li key={eintrag.name} className="flex items-center gap-1.5">
                    <span aria-hidden="true" className="size-2.5 rounded-sm" style={eintrag.stil}/>
                    {eintrag.name}
                </li>
            ))}
        </ul>
    );
}

function summe(monat: StatistikMonat): number {
    return monat.spesen + monat.fahrt_erfasst + monat.fahrt_geschaetzt;
}

function MonatsZeile({monat, maximum}: {monat: StatistikMonat; maximum: number}) {
    const teile = [
        {wert: monat.spesen, name: 'Spesen', stil: {background: 'var(--diagramm-spesen)'}},
        {wert: monat.fahrt_erfasst, name: 'Fahrtkosten', stil: {background: 'var(--diagramm-fahrt)'}},
        {wert: monat.fahrt_geschaetzt, name: 'Fahrtkosten geschätzt',
            stil: {background: SCHRAFFUR, boxShadow: 'inset 0 0 0 1px var(--diagramm-fahrt)'}},
    ].filter((teil) => teil.wert > 0);
    const geschaetzt = monat.fahrt_geschaetzt > 0;
    const beschreibung = [
        `${monatsName(monat.monat)}: ${monat.spiele} ${monat.spiele === 1 ? 'Spiel' : 'Spiele'}`,
        ...teile.map((teil) => `${teil.name} ${formatEuro(teil.wert)}`),
    ].join(' · ');

    return (
        <li className="grid grid-cols-[4.5rem_1fr_auto] items-center gap-3 text-sm" title={beschreibung}>
            <span className="text-xs text-muted-foreground">{monatsName(monat.monat)}</span>
            <span className="flex h-3 min-w-0 gap-[2px]" aria-hidden="true">
                {teile.map((teil, index) => (
                    <span
                        key={teil.name}
                        className={[
                            'h-full',
                            index === 0 ? 'rounded-l' : '',
                            index === teile.length - 1 ? 'rounded-r' : '',
                        ].join(' ')}
                        style={{...teil.stil, width: `${(teil.wert / maximum) * 100}%`}}
                    />
                ))}
            </span>
            <span className="text-right font-mono text-xs tabular-nums">
                <span className="sr-only">{beschreibung}. Summe </span>
                {geschaetzt ? '≈ ' : ''}{formatEuro(summe(monat))}
            </span>
        </li>
    );
}

/**
 * Expenses and travel costs of the own matches of a season. Where no
 * travel costs are entered, the server estimates them from the route from the
 * own home address - this always appears here marked as "geschätzt".
 */
export function SpesenStatistik({saison, onGeladen}: SpesenStatistikProps) {
    const [daten, setDaten] = useState<Statistik | null>(null);
    const [fehler, setFehler] = useState(false);
    // A ref, so a new callback identity does not restart the polling
    const onGeladenRef = useRef(onGeladen);
    useEffect(() => {
        onGeladenRef.current = onGeladen;
    }, [onGeladen]);

    useEffect(() => {
        let aktiv = true;
        let timer: ReturnType<typeof setTimeout> | undefined;
        let versuche = 0;
        let ohneFortschritt = 0;
        let vorherOffen = Infinity;

        // The server only looks up for a few seconds per call; whatever
        // stays open is picked up by the next request - until nothing progresses any more
        const laden = () => {
            getStatistik(saison)
                .then((antwort) => {
                    if (!aktiv) return;
                    setDaten(antwort);
                    onGeladenRef.current?.(antwort);
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
    }, [saison]);

    const kopf = (
        <CardHeader className="flex h-11 flex-row items-center gap-2 px-4 py-0 sm:px-6">
            <Euro className="size-4 text-muted-foreground"/>
            <CardTitle className="text-sm">Spesen & Fahrtkosten</CardTitle>
        </CardHeader>
    );

    let inhalt;
    if (fehler) {
        inhalt = <p className="text-sm text-muted-foreground">Die Statistik konnte nicht geladen werden.</p>;
    } else if (!daten) {
        inhalt = (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin"/>
                Rechne…
            </p>
        );
    } else if (!daten.saison || (saison !== null && daten.saison !== saison) || (daten.spiele === 0 && daten.ohne_rolle === 0)) {
        inhalt = (
            <p className="text-sm text-muted-foreground">
                {saison ?? daten.saison ? `Für ${saison ?? daten.saison} liegen` : 'Noch liegen'} keine vergangenen
                Ansetzungen in Spesenfuchs vor. Die Statistik rechnet mit den Spielen, die seit dem
                ersten Abruf hier gespeichert sind.
            </p>
        );
    } else {
        const fahrt = daten.fahrtkosten;
        const maximum = Math.max(...daten.monate.map(summe), 0.01);
        inhalt = (
            <div className="space-y-5">
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                    <Kennzahl
                        label="Spesen"
                        wert={formatEuro(daten.spesen)}
                        zusatz={`${daten.spiele} ${daten.spiele === 1 ? 'Spiel' : 'Spiele'}`}
                    />
                    <Kennzahl
                        label="Fahrtkosten"
                        wert={`${fahrt.geschaetzt > 0 ? '≈ ' : ''}${formatEuro(fahrt.erfasst + fahrt.geschaetzt)}`}
                        zusatz={fahrt.geschaetzt > 0 ? `davon ${formatEuro(fahrt.geschaetzt)} geschätzt` : 'alle eingetragen'}
                    />
                    <Kennzahl
                        label="Zusammen"
                        wert={`${fahrt.geschaetzt > 0 ? '≈ ' : ''}${formatEuro(daten.gesamt)}`}
                        zusatz={daten.spiele > 0 ? `Ø ${formatEuro(daten.gesamt / daten.spiele)} je Spiel` : undefined}
                    />
                </div>

                {daten.monate.length > 0 && (
                    <div className="space-y-2">
                        <Legende/>
                        <ul className="space-y-1.5">
                            {daten.monate.map((monat) => (
                                <MonatsZeile key={monat.monat} monat={monat} maximum={maximum}/>
                            ))}
                        </ul>
                    </div>
                )}

                <div className="space-y-1 text-xs text-muted-foreground">
                    {daten.rollen.length > 0 && (
                        <p>
                            {daten.rollen.map((r) => `${r.rolle}: ${r.spiele} ${r.spiele === 1 ? 'Spiel' : 'Spiele'}, ${formatEuro(r.spesen)}`).join(' · ')}
                        </p>
                    )}
                    {fahrt.geschaetzt_spiele > 0 && (
                        <p>
                            Geschätzt für {fahrt.geschaetzt_spiele} {fahrt.geschaetzt_spiele === 1 ? 'Spiel' : 'Spiele'} ohne
                            eingetragene Fahrtkosten: allein vom eigenen Wohnort zum Platz und zurück,
                            zusammen {fahrt.geschaetzt_km.toLocaleString('de-DE')} km
                            {fahrt.luftlinie_spiele > 0 && ' (teils nur über die Luftlinie)'}.
                        </p>
                    )}
                    {fahrt.ohne_schaetzung > 0 && (
                        <p>Ohne Schätzung, weil eine Anschrift fehlt: {fahrt.ohne_schaetzung} {fahrt.ohne_schaetzung === 1 ? 'Spiel' : 'Spiele'}.</p>
                    )}
                    {daten.ohne_rolle > 0 && (
                        <p>
                            Nicht gezählt: {daten.ohne_rolle} {daten.ohne_rolle === 1 ? 'Spiel' : 'Spiele'}, in
                            denen die eigene Rolle nicht erkennbar ist – der nächste Abruf trägt sie nach.
                        </p>
                    )}
                    <p>
                        {daten.quelle === 'dfbnet'
                            ? 'Gezählt sind die Spiele, die DFBnet als geleitet führt – dieselben wie im Reiter Saison.'
                            : 'Für diese Saison liegt die Liste der geleiteten Spiele aus DFBnet noch nicht vor – gezählt sind die Ansetzungen, die nicht zurückgezogen wurden.'}
                    </p>
                    {daten.ohne_ansetzung > 0 && (
                        <p>
                            Für {daten.ohne_ansetzung} {daten.ohne_ansetzung === 1 ? 'Spiel' : 'Spiele'} gibt es keine
                            gespeicherte Ansetzung (vor deinem ersten Abruf): Spesen nach der Spielklasse berechnet,
                            Fahrtkosten geschätzt.
                        </p>
                    )}
                    {daten.ohne_satz > 0 && (
                        <p>
                            Ohne Spesensatz: {daten.ohne_satz} {daten.ohne_satz === 1 ? 'Spiel' : 'Spiele'} – etwa
                            Junioren-Bundesliga (zahlt der DFB), Beobachtungen oder Pokal- und Freundschaftsspiele,
                            deren Klasse sich nicht bestimmen lässt.
                        </p>
                    )}
                    {daten.offen > 0 && (
                        <p className="flex items-center gap-1.5">
                            <Loader2 className="size-3 animate-spin"/>
                            Noch {daten.offen} Strecken in Berechnung…
                        </p>
                    )}
                </div>

                {daten.monate.length > 0 && (
                    <details className="text-xs">
                        <summary className="cursor-pointer text-muted-foreground">Als Tabelle</summary>
                        <table className="mt-2 w-full text-left tabular-nums">
                            <thead className="text-muted-foreground">
                                <tr>
                                    <th className="py-1 font-normal">Monat</th>
                                    <th className="py-1 text-right font-normal">Spiele</th>
                                    <th className="py-1 text-right font-normal">Spesen</th>
                                    <th className="py-1 text-right font-normal">Fahrt</th>
                                    <th className="py-1 text-right font-normal">geschätzt</th>
                                </tr>
                            </thead>
                            <tbody>
                                {daten.monate.map((m) => (
                                    <tr key={m.monat} className="border-t">
                                        <td className="py-1">{monatsName(m.monat)}</td>
                                        <td className="py-1 text-right">{m.spiele}</td>
                                        <td className="py-1 text-right">{formatEuro(m.spesen)}</td>
                                        <td className="py-1 text-right">{formatEuro(m.fahrt_erfasst)}</td>
                                        <td className="py-1 text-right">{formatEuro(m.fahrt_geschaetzt)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </details>
                )}
            </div>
        );
    }

    return (
        <Card className="gap-0 overflow-hidden py-0">
            {kopf}
            <Separator/>
            <CardContent className="p-4 sm:p-6">{inhalt}</CardContent>
        </Card>
    );
}
