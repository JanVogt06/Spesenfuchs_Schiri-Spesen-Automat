import {Card, CardContent, CardHeader, CardTitle} from '@/components/ui/card';
import {Separator} from '@/components/ui/separator';
import {Badge} from '@/components/ui/badge';
import {ChevronDown, ClipboardCheck} from 'lucide-react';
import {
    formatDatum,
    formatSchnitt,
    nachStaffel,
    ROLLEN_GRUPPEN,
    ROLLEN_NAMEN,
    schnitte,
    type Beobachtung,
} from '@/lib/beobachtungen';

interface BeobachtungsKarteProps {
    titel: string;
    untertitel: string;
    beobachtungen: Beobachtung[];
    /** false: die Saison ist für diese Quelle noch nicht abgerufen */
    gelesen: boolean;
    /** Zusätzliche Schnitte je Spielklasse (nur Herren) */
    mitSpielklassen?: boolean;
}

function anzahlText(n: number): string {
    return `${n} ${n === 1 ? 'Beobachtung' : 'Beobachtungen'}`;
}

/** Die Schnitte je Spielklasse - nur sinnvoll, wenn es mehr als eine gibt */
function Spielklassen({beobachtungen}: {beobachtungen: Beobachtung[]}) {
    const staffeln = nachStaffel(beobachtungen).map((g) => ({...g, schnitte: schnitte(g.beobachtungen)}));
    const gruppen = ROLLEN_GRUPPEN.filter(({gruppe}) =>
        staffeln.some((s) => s.schnitte.some((x) => x.gruppe === gruppe))
    );

    return (
        <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
                <thead>
                    <tr className="border-b text-xs tracking-wide text-muted-foreground uppercase">
                        <th className="px-3 py-2 text-left font-medium">Spielklasse</th>
                        {gruppen.map(({gruppe, label}) => (
                            <th key={gruppe} className="px-3 py-2 text-right font-medium">{label}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {staffeln.map((s) => (
                        <tr key={s.staffel} className="border-b last:border-0">
                            <td className="px-3 py-2">{s.staffel}</td>
                            {gruppen.map(({gruppe}) => {
                                const x = s.schnitte.find((y) => y.gruppe === gruppe);
                                return (
                                    <td key={gruppe} className="px-3 py-2 text-right whitespace-nowrap">
                                        {x ? (
                                            <>
                                                <span className="font-mono">{formatSchnitt(x.schnitt)}</span>
                                                <span className="ml-1 text-xs text-muted-foreground">({x.anzahl})</span>
                                            </>
                                        ) : (
                                            <span className="text-muted-foreground">–</span>
                                        )}
                                    </td>
                                );
                            })}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

function Einzelliste({beobachtungen}: {beobachtungen: Beobachtung[]}) {
    return (
        <details className="group rounded-lg border">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-2.5 text-sm font-medium select-none [&::-webkit-details-marker]:hidden">
                Einzelne Beobachtungen
                <span className="flex items-center gap-2 text-xs font-normal text-muted-foreground">
                    {beobachtungen.length}
                    <ChevronDown className="size-4 transition-transform group-open:rotate-180"/>
                </span>
            </summary>

            {/* Breite Ansicht: Tabelle */}
            <div className="hidden overflow-x-auto border-t lg:block">
                <table className="w-full text-sm">
                    <thead>
                        <tr className="border-b text-xs tracking-wide text-muted-foreground uppercase">
                            <th className="px-3 py-2 text-left font-medium">Datum</th>
                            <th className="px-3 py-2 text-left font-medium">Spielklasse</th>
                            <th className="px-3 py-2 text-left font-medium">Spiel</th>
                            <th className="px-3 py-2 text-center font-medium">Erg.</th>
                            <th className="px-3 py-2 text-left font-medium">Rolle</th>
                            <th className="px-3 py-2 text-left font-medium">Beobachter</th>
                            <th className="px-3 py-2 text-right font-medium">Note</th>
                        </tr>
                    </thead>
                    <tbody>
                        {beobachtungen.map((b) => (
                            <tr key={b.id} className="border-b last:border-0 align-top">
                                <td className="px-3 py-2 whitespace-nowrap">
                                    {formatDatum(b.datum)}
                                    {b.uhrzeit && <span className="block text-xs text-muted-foreground">{b.uhrzeit}</span>}
                                </td>
                                <td className="px-3 py-2">{b.staffel}</td>
                                <td className="px-3 py-2">{b.heim} – {b.gast}</td>
                                <td className="px-3 py-2 text-center font-mono whitespace-nowrap">{b.ergebnis}</td>
                                <td className="px-3 py-2 whitespace-nowrap">{ROLLEN_NAMEN[b.rolle] ?? b.rolle}</td>
                                <td className="px-3 py-2">{b.beobachter}</td>
                                <td className="px-3 py-2 text-right font-mono font-medium">{b.note_text || b.note}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {/* Schmale Ansicht: Karten */}
            <div className="space-y-2 border-t p-3 lg:hidden">
                {beobachtungen.map((b) => (
                    <div key={b.id} className="rounded-lg border border-dashed p-3 text-sm">
                        <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                                <p className="font-medium break-words">{b.heim} – {b.gast}</p>
                                <p className="text-xs text-muted-foreground">
                                    {formatDatum(b.datum)} · {b.staffel}{b.ergebnis && ` · ${b.ergebnis}`}
                                </p>
                            </div>
                            <span className="shrink-0 font-mono text-base font-semibold">{b.note_text || b.note}</span>
                        </div>
                        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                            <Badge variant="secondary" className="font-normal">{ROLLEN_NAMEN[b.rolle] ?? b.rolle}</Badge>
                            {b.beobachter && <span className="text-muted-foreground">Beobachter: {b.beobachter}</span>}
                        </div>
                    </div>
                ))}
            </div>
        </details>
    );
}

export function BeobachtungsKarte({titel, untertitel, beobachtungen, gelesen, mitSpielklassen}: BeobachtungsKarteProps) {
    const werte = schnitte(beobachtungen);
    const mehrereKlassen = mitSpielklassen && nachStaffel(beobachtungen).length > 1;

    return (
        <Card className="gap-0 overflow-hidden py-0">
            <CardHeader className="flex min-h-11 flex-row items-center justify-between gap-2 px-4 py-2 sm:px-6">
                <div className="flex min-w-0 items-center gap-2">
                    <ClipboardCheck className="size-4 shrink-0 text-muted-foreground"/>
                    <CardTitle className="truncate text-sm">{titel}</CardTitle>
                    <span className="truncate text-xs text-muted-foreground">{untertitel}</span>
                </div>
                {beobachtungen.length > 0 && (
                    <span className="shrink-0 text-xs text-muted-foreground">{anzahlText(beobachtungen.length)}</span>
                )}
            </CardHeader>
            <Separator/>
            <CardContent className="space-y-4 p-4 sm:p-6">
                {!gelesen ? (
                    <p className="text-sm text-muted-foreground">
                        Diese Saison ist noch nicht abgerufen. Sie wird beim nächsten Abruf aus DFBnet mitgeladen.
                    </p>
                ) : beobachtungen.length === 0 ? (
                    <p className="text-sm text-muted-foreground">Keine Beobachtung in dieser Saison.</p>
                ) : (
                    <>
                        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                            {werte.map((x) => (
                                <div key={x.gruppe} className="rounded-lg border bg-muted/20 p-3">
                                    <p className="text-xs text-muted-foreground">{x.label}</p>
                                    <p className="mt-1 font-mono text-2xl font-semibold tracking-tight">
                                        <span className="mr-1 text-base font-normal text-muted-foreground">Ø</span>
                                        {formatSchnitt(x.schnitt)}
                                    </p>
                                    <p className="text-xs text-muted-foreground">{anzahlText(x.anzahl)}</p>
                                </div>
                            ))}
                        </div>

                        {mehrereKlassen && <Spielklassen beobachtungen={beobachtungen}/>}

                        <Einzelliste beobachtungen={beobachtungen}/>
                    </>
                )}
            </CardContent>
        </Card>
    );
}
