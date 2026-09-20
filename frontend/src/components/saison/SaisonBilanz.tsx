import {Card, CardContent, CardHeader, CardTitle} from '@/components/ui/card';
import {Separator} from '@/components/ui/separator';
import {ClipboardList, GraduationCap} from 'lucide-react';
import type {SaisonEinsatz, SaisonLehrgaenge} from '@/lib/saison';

interface SaisonBilanzProps {
    einsaetze: SaisonEinsatz[];
    lehrgaenge: SaisonLehrgaenge | null;
}

const LEHRGANG_NAMEN: Record<keyof Omit<SaisonLehrgaenge, 'scraped_at'>, string> = {
    lehrabend: 'Lehrabend',
    lehrabend_online: 'Lehrabend (online)',
    leistungspruefung: 'Leistungsprüfung',
};

/** DFBnet schreibt "-" für "nichts erfasst" - das bleibt so stehen */
function wert(text: string): string {
    return text && text.trim() ? text : '–';
}

export function SaisonBilanz({einsaetze, lehrgaenge}: SaisonBilanzProps) {
    const zeilen = einsaetze.filter((e) => e.rolle !== 'Summe');
    const summe = einsaetze.find((e) => e.rolle === 'Summe');

    return (
        <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
            <Card className="gap-0 overflow-hidden py-0">
                <CardHeader className="flex h-11 flex-row items-center gap-2 px-4 py-0 sm:px-6">
                    <ClipboardList className="size-4 text-muted-foreground"/>
                    <CardTitle className="text-sm">Anrechenbare Einsätze</CardTitle>
                </CardHeader>
                <Separator/>
                <CardContent className="p-0">
                    {zeilen.length === 0 ? (
                        <p className="px-4 py-6 text-sm text-muted-foreground sm:px-6">
                            Für diese Saison ist keine Einsatzbilanz gespeichert.
                        </p>
                    ) : (
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="border-b text-xs tracking-wide text-muted-foreground uppercase">
                                        <th className="px-4 py-2 text-left font-medium sm:px-6">Rolle</th>
                                        <th className="px-3 py-2 text-right font-medium">Geleitet</th>
                                        <th className="px-3 py-2 text-right font-medium">Zurückgegeben</th>
                                        <th className="px-4 py-2 text-right font-medium sm:px-6">Nicht angetreten</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {zeilen.map((zeile) => (
                                        <tr key={zeile.rolle} className="border-b last:border-0">
                                            <td className="px-4 py-2 sm:px-6">{zeile.rolle}</td>
                                            <td className="px-3 py-2 text-right font-mono">{wert(zeile.geleitet)}</td>
                                            <td className="px-3 py-2 text-right font-mono">{wert(zeile.zurueckgegeben)}</td>
                                            <td className="px-4 py-2 text-right font-mono sm:px-6">{wert(zeile.nicht_angetreten)}</td>
                                        </tr>
                                    ))}
                                    {summe && (
                                        <tr className="bg-muted/40 font-medium">
                                            <td className="px-4 py-2 sm:px-6">Summe</td>
                                            <td className="px-3 py-2 text-right font-mono">{wert(summe.geleitet)}</td>
                                            <td className="px-3 py-2 text-right font-mono">{wert(summe.zurueckgegeben)}</td>
                                            <td className="px-4 py-2 text-right font-mono sm:px-6">{wert(summe.nicht_angetreten)}</td>
                                        </tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    )}
                </CardContent>
            </Card>

            <Card className="gap-0 overflow-hidden py-0">
                <CardHeader className="flex h-11 flex-row items-center gap-2 px-4 py-0 sm:px-6">
                    <GraduationCap className="size-4 text-muted-foreground"/>
                    <CardTitle className="text-sm">Lehrabende &amp; Prüfungen</CardTitle>
                </CardHeader>
                <Separator/>
                <CardContent className="p-4 sm:p-6">
                    {lehrgaenge ? (
                        <div className="grid gap-1.5 text-sm">
                            {(Object.keys(LEHRGANG_NAMEN) as (keyof typeof LEHRGANG_NAMEN)[]).map((feld) => (
                                <div key={feld} className="grid grid-cols-[1fr_auto] gap-2">
                                    <span className="text-muted-foreground">{LEHRGANG_NAMEN[feld]}</span>
                                    <span className="font-mono">{wert(lehrgaenge[feld])}</span>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <p className="text-sm text-muted-foreground">
                            Für diese Saison ist nichts gespeichert.
                        </p>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
