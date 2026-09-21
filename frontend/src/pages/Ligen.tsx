import {useState, useEffect} from 'react';
import {Button} from '@/components/ui/button';
import {AppShell} from '@/components/layout/AppShell';
import {getLigen, tordifferenz, type LigenAntwort, type Staffel} from '@/lib/ligen';
import {AlertCircle, Loader2, Table2} from 'lucide-react';
import {cn} from '@/lib/utils';

function fehlertext(err: unknown, fallback: string): string {
    const detail = (err as {response?: {data?: {error?: {message?: string}}}})
        ?.response?.data?.error?.message;
    return detail || fallback;
}

function abgeglichen(zeitpunkt: string | null): string {
    if (!zeitpunkt) return '';
    const datum = new Date(zeitpunkt);
    if (Number.isNaN(datum.getTime())) return '';
    return datum.toLocaleString('de-DE', {dateStyle: 'medium', timeStyle: 'short'});
}

function Tabelle({staffel}: {staffel: Staffel}) {
    if (staffel.tabelle.length === 0) {
        return (
            <p className="rounded-lg border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
                Für diese Staffel liegt noch keine Tabelle vor.
            </p>
        );
    }

    return (
        <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
                <thead className="border-b bg-muted/40 text-xs text-muted-foreground">
                    <tr>
                        <th className="w-10 px-3 py-2 text-right font-medium">#</th>
                        <th className="px-3 py-2 text-left font-medium">Mannschaft</th>
                        <th className="w-12 px-2 py-2 text-right font-medium">Sp</th>
                        <th className="hidden w-10 px-2 py-2 text-right font-medium sm:table-cell">S</th>
                        <th className="hidden w-10 px-2 py-2 text-right font-medium sm:table-cell">U</th>
                        <th className="hidden w-10 px-2 py-2 text-right font-medium sm:table-cell">N</th>
                        <th className="w-16 px-2 py-2 text-right font-medium">Tore</th>
                        <th className="hidden w-12 px-2 py-2 text-right font-medium sm:table-cell">Diff</th>
                        <th className="w-12 px-3 py-2 text-right font-medium">Pkt</th>
                    </tr>
                </thead>
                <tbody>
                    {staffel.tabelle.map((platz) => (
                        <tr key={platz.team_id} className="border-b last:border-0">
                            <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
                                {platz.platz}
                            </td>
                            <td className="px-3 py-2 font-medium">{platz.mannschaft}</td>
                            <td className="px-2 py-2 text-right tabular-nums">{platz.spiele}</td>
                            <td className="hidden px-2 py-2 text-right tabular-nums sm:table-cell">{platz.siege}</td>
                            <td className="hidden px-2 py-2 text-right tabular-nums sm:table-cell">{platz.unentschieden}</td>
                            <td className="hidden px-2 py-2 text-right tabular-nums sm:table-cell">{platz.niederlagen}</td>
                            <td className="px-2 py-2 text-right tabular-nums whitespace-nowrap">
                                {platz.tore}:{platz.gegentore}
                            </td>
                            <td className="hidden px-2 py-2 text-right tabular-nums text-muted-foreground sm:table-cell">
                                {tordifferenz(platz)}
                            </td>
                            <td className="px-3 py-2 text-right font-semibold tabular-nums">{platz.punkte}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

export function LigenPage() {
    const [daten, setDaten] = useState<LigenAntwort | null>(null);
    const [gewaehlt, setGewaehlt] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [ladeFehler, setLadeFehler] = useState('');

    useEffect(() => {
        getLigen()
            .then((antwort) => {
                setDaten(antwort);
                setGewaehlt(antwort.staffeln.length > 0 ? antwort.staffeln[0].staffel_id : null);
            })
            .catch((err: unknown) => setLadeFehler(fehlertext(err, 'Die Ligatabellen konnten nicht geladen werden.')))
            .finally(() => setIsLoading(false));
    }, []);

    const staffel = daten?.staffeln.find((eintrag) => eintrag.staffel_id === gewaehlt) ?? null;

    return (
        <AppShell>
            {ladeFehler && (
                <div className="mb-6 flex items-start gap-2 rounded-lg bg-destructive/10 px-4 py-3 ring-1 ring-destructive/20">
                    <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive"/>
                    <p className="text-sm break-words text-destructive">{ladeFehler}</p>
                </div>
            )}

            {isLoading ? (
                <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed px-3 py-12 text-sm text-muted-foreground">
                    <Loader2 className="size-5 animate-spin"/>
                    Lade Ligatabellen...
                </div>
            ) : !daten || daten.staffeln.length === 0 ? (
                <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed px-3 py-12 text-center">
                    <span className="grid size-14 place-items-center rounded-2xl border border-dashed bg-muted/30">
                        <Table2 className="size-6 text-muted-foreground"/>
                    </span>
                    <p className="text-sm font-medium">Noch keine Ligatabellen</p>
                    <p className="max-w-sm text-sm text-muted-foreground">
                        Sie werden in der Nacht von FUSSBALL.DE geholt. Als Ausgangspunkt dienen
                        eigene Ansetzungen aus Verbandsliga und Landesklasse – ohne solche bleiben
                        die Tabellen leer.
                    </p>
                </div>
            ) : (
                <div className="space-y-4">
                    <div>
                        <h1 className="text-lg font-semibold tracking-tight">Ligen</h1>
                        <p className="text-sm text-muted-foreground">
                            Grundlage der Spesen bei Pokal- und Freundschaftsspielen im Herrenbereich.
                            {daten.bestand.aktualisiert_at && (
                                <> Zuletzt abgeglichen am {abgeglichen(daten.bestand.aktualisiert_at)}.</>
                            )}
                        </p>
                    </div>

                    <div className="flex flex-wrap gap-1.5">
                        {daten.staffeln.map((eintrag) => (
                            <Button
                                key={eintrag.staffel_id}
                                variant="ghost"
                                size="sm"
                                onClick={() => setGewaehlt(eintrag.staffel_id)}
                                className={cn(
                                    'text-muted-foreground',
                                    gewaehlt === eintrag.staffel_id &&
                                        'bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary'
                                )}
                            >
                                {eintrag.anzeigename}
                                <span className="ml-1 text-xs opacity-70">({eintrag.mannschaften})</span>
                            </Button>
                        ))}
                    </div>

                    {staffel && <Tabelle staffel={staffel}/>}
                </div>
            )}
        </AppShell>
    );
}
