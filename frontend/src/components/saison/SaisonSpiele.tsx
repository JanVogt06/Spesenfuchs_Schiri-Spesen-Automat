import {Card, CardContent, CardHeader, CardTitle} from '@/components/ui/card';
import {Separator} from '@/components/ui/separator';
import {Badge} from '@/components/ui/badge';
import {Calendar} from 'lucide-react';
import {formatKarte, summeKarten, type SaisonSpiel} from '@/lib/saison';

interface SaisonSpieleProps {
    spiele: SaisonSpiel[];
}

/** "2026-09-20" -> "20.09.2026" */
function formatDatum(iso: string): string {
    const teile = (iso || '').split('-');
    return teile.length === 3 ? `${teile[2]}.${teile[1]}.${teile[0]}` : iso;
}

function gespannText(spiel: SaisonSpiel): string {
    return spiel.gespann.map((p) => `${p.rolle} ${p.name}`).join(' · ');
}

/**
 * Kartenspalten in der Reihenfolge der DFBnet-Tabelle.
 *
 * Die drei Karten je Mannschaft stehen dort nur als Symbole im Kopf; hier
 * tragen sie ein Kürzel, damit die Spalte ohne Legende lesbar bleibt.
 */
const KARTEN: {feld: keyof SaisonSpiel; kurz: string; titel: string}[] = [
    {feld: 'heim_gelb', kurz: 'G', titel: 'Heim: Gelbe Karten'},
    {feld: 'heim_gelbrot', kurz: 'GR', titel: 'Heim: Gelb-Rote Karten'},
    {feld: 'heim_rot', kurz: 'R', titel: 'Heim: Rote Karten'},
    {feld: 'gast_gelb', kurz: 'G', titel: 'Gast: Gelbe Karten'},
    {feld: 'gast_gelbrot', kurz: 'GR', titel: 'Gast: Gelb-Rote Karten'},
    {feld: 'gast_rot', kurz: 'R', titel: 'Gast: Rote Karten'},
];

export function SaisonSpiele({spiele}: SaisonSpieleProps) {
    if (spiele.length === 0) {
        return (
            <Card className="gap-0 overflow-hidden py-0">
                <CardHeader className="flex h-11 flex-row items-center gap-2 px-4 py-0 sm:px-6">
                    <Calendar className="size-4 text-muted-foreground"/>
                    <CardTitle className="text-sm">Geleitete Spiele</CardTitle>
                </CardHeader>
                <Separator/>
                <CardContent className="p-6">
                    <p className="text-sm text-muted-foreground">
                        In dieser Saison ist kein geleitetes Spiel verzeichnet.
                    </p>
                </CardContent>
            </Card>
        );
    }

    return (
        <Card className="gap-0 overflow-hidden py-0">
            <CardHeader className="flex h-11 flex-row items-center justify-between gap-2 px-4 py-0 sm:px-6">
                <div className="flex items-center gap-2">
                    <Calendar className="size-4 text-muted-foreground"/>
                    <CardTitle className="text-sm">Geleitete Spiele</CardTitle>
                </div>
                <span className="text-xs text-muted-foreground">
                    {spiele.length} {spiele.length === 1 ? 'Spiel' : 'Spiele'}
                </span>
            </CardHeader>
            <Separator/>

            {/* Breite Ansicht: die Tabelle wie in DFBnet */}
            <CardContent className="hidden p-0 lg:block">
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead>
                            {/* Zweizeilig wie in DFBnet: die Karten stehen dort unter einer
                                gemeinsamen Ueberschrift je Mannschaft. Einzeilig waere
                                "G" fuer Gast und "G" fuer Gelb nicht zu unterscheiden. */}
                            <tr className="text-xs tracking-wide text-muted-foreground uppercase">
                                <th className="px-4 pt-2 text-left font-medium sm:px-6" rowSpan={2}>Datum</th>
                                <th className="px-3 pt-2 text-left font-medium" rowSpan={2}>Liga</th>
                                <th className="px-3 pt-2 text-left font-medium" rowSpan={2}>Heim</th>
                                <th className="px-3 pt-2 text-left font-medium" rowSpan={2}>Gast</th>
                                <th className="px-3 pt-2 text-center font-medium" rowSpan={2}>Erg.</th>
                                <th className="border-l px-1.5 pt-2 text-center font-medium" colSpan={3}>Heim</th>
                                <th className="border-l px-1.5 pt-2 text-center font-medium" colSpan={3}>Gast</th>
                                <th className="border-l px-4 pt-2 text-left font-medium sm:px-6" rowSpan={2}>Gespann</th>
                            </tr>
                            <tr className="border-b text-xs text-muted-foreground">
                                {KARTEN.map((karte, i) => (
                                    <th
                                        key={karte.feld}
                                        title={karte.titel}
                                        className={`px-1.5 pb-2 text-center font-medium ${i % 3 === 0 ? 'border-l' : ''}`}
                                    >
                                        {karte.kurz}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {spiele.map((spiel) => (
                                <tr key={spiel.id} className="border-b last:border-0 align-top">
                                    <td className="px-4 py-2 whitespace-nowrap sm:px-6">
                                        {formatDatum(spiel.datum)}
                                        {spiel.uhrzeit && (
                                            <span className="block text-xs text-muted-foreground">{spiel.uhrzeit}</span>
                                        )}
                                    </td>
                                    <td className="px-3 py-2">{spiel.liga}</td>
                                    <td className="px-3 py-2">{spiel.heim}</td>
                                    <td className="px-3 py-2">{spiel.gast}</td>
                                    <td className="px-3 py-2 text-center font-mono whitespace-nowrap">{spiel.ergebnis}</td>
                                    {KARTEN.map((karte, i) => (
                                        <td
                                            key={karte.feld}
                                            className={`px-1.5 py-2 text-center font-mono ${i % 3 === 0 ? 'border-l' : ''}`}
                                        >
                                            {formatKarte(spiel[karte.feld] as number | null)}
                                        </td>
                                    ))}
                                    <td className="border-l px-4 py-2 sm:px-6">
                                        <div className="space-y-0.5">
                                            {spiel.gespann.map((person, index) => (
                                                <div key={`${person.rolle}-${index}`} className="flex gap-2">
                                                    <span className="w-12 shrink-0 text-xs text-muted-foreground">
                                                        {person.rolle}
                                                    </span>
                                                    <span className={person.ist_selbst ? 'font-medium text-primary' : ''}>
                                                        {person.name}
                                                    </span>
                                                </div>
                                            ))}
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                        <tfoot>
                            <tr className="bg-muted/40 text-xs font-medium">
                                <td className="px-4 py-2 sm:px-6" colSpan={4}>Summe Karten</td>
                                <td/>
                                {KARTEN.map((karte, i) => (
                                    <td
                                        key={karte.feld}
                                        className={`px-1.5 py-2 text-center font-mono ${i % 3 === 0 ? 'border-l' : ''}`}
                                    >
                                        {summeKarten(spiele, karte.feld)}
                                    </td>
                                ))}
                                <td className="border-l"/>
                            </tr>
                        </tfoot>
                    </table>
                </div>
            </CardContent>

            {/* Schmale Ansicht: dieselben Daten als Karten, die Tabelle passt nicht aufs Handy */}
            <CardContent className="space-y-3 p-4 lg:hidden">
                {spiele.map((spiel) => (
                    <div key={spiel.id} className="rounded-lg border border-dashed p-3 text-sm">
                        <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                                <p className="font-medium break-words">
                                    {spiel.heim} – {spiel.gast}
                                </p>
                                <p className="text-xs text-muted-foreground">
                                    {formatDatum(spiel.datum)}{spiel.uhrzeit && `, ${spiel.uhrzeit}`} · {spiel.liga}
                                </p>
                            </div>
                            <span className="shrink-0 font-mono font-medium">{spiel.ergebnis}</span>
                        </div>

                        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                            {spiel.eigene_rolle && (
                                <Badge variant="secondary" className="font-normal">{spiel.eigene_rolle}</Badge>
                            )}
                            <span className="text-muted-foreground">
                                H {formatKarte(spiel.heim_gelb)}/{formatKarte(spiel.heim_gelbrot)}/{formatKarte(spiel.heim_rot)}
                            </span>
                            <span className="text-muted-foreground">
                                G {formatKarte(spiel.gast_gelb)}/{formatKarte(spiel.gast_gelbrot)}/{formatKarte(spiel.gast_rot)}
                            </span>
                        </div>

                        {spiel.gespann.length > 0 && (
                            <p className="mt-1.5 text-xs break-words text-muted-foreground">
                                {gespannText(spiel)}
                            </p>
                        )}
                    </div>
                ))}
            </CardContent>
        </Card>
    );
}
