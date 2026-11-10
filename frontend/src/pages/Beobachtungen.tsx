import {useState, useEffect, useCallback, useMemo} from 'react';
import {Button} from '@/components/ui/button';
import {AppShell} from '@/components/layout/AppShell';
import {GenerateButton} from '@/components/matches/GenerateButton';
import {BeobachtungsKarte} from '@/components/beobachtungen/BeobachtungsKarte';
import {useScrapeRun} from '@/hooks/useScrapeRun';
import {angeboteneSaisons, getBeobachtungen, nachStaffel, type BeobachtungsDaten} from '@/lib/beobachtungen';
import {AlertCircle, ClipboardCheck, Loader2} from 'lucide-react';
import {cn} from '@/lib/utils';

function fehlertext(err: unknown, fallback: string): string {
    const detail = (err as {response?: {data?: {error?: {message?: string}}}})
        ?.response?.data?.error?.message;
    return detail || fallback;
}

export function BeobachtungenPage() {
    const [daten, setDaten] = useState<BeobachtungsDaten | null>(null);
    const [gewaehlt, setGewaehlt] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [ladeFehler, setLadeFehler] = useState('');

    const saisons = useMemo(() => (daten ? angeboteneSaisons(daten) : []), [daten]);

    const loadDaten = useCallback(async () => {
        try {
            const neu = await getBeobachtungen();
            setDaten(neu);
            setLadeFehler('');

            // Beim ersten Laden die neueste Saison; nach einem Abruf die
            // gewaehlte behalten, solange es sie noch gibt.
            const liste = angeboteneSaisons(neu);
            setGewaehlt((bisher) => (bisher && liste.includes(bisher) ? bisher : liste[0] ?? null));
        } catch (err: unknown) {
            setLadeFehler(fehlertext(err, 'Die Beobachtungen konnten nicht geladen werden.'));
        } finally {
            setIsLoading(false);
        }
    }, []);

    // Die Beobachtungen werden beim regulaeren Abruf mitgelesen
    const {run, isRunning, isStarting, error, startGeneration} = useScrapeRun(loadDaten);

    useEffect(() => {
        loadDaten();
    }, [loadDaten]);

    const anzahlJeSaison = useMemo(() => {
        const zaehler = new Map<string, number>();
        for (const b of daten?.beobachtungen ?? []) zaehler.set(b.saison, (zaehler.get(b.saison) ?? 0) + 1);
        return zaehler;
    }, [daten]);

    const inSaison = (daten?.beobachtungen ?? []).filter((b) => b.saison === gewaehlt);
    const herren = inSaison.filter((b) => b.quelle === 'herren');
    const portal = nachStaffel(inSaison.filter((b) => b.quelle === 'portal'));
    const herrenGelesen = !!daten?.saisons.some((s) => s.quelle === 'herren' && s.saison === gewaehlt);

    const displayError = error || ladeFehler;

    return (
        <AppShell actions={<GenerateButton isGenerating={isStarting || isRunning} onClick={startGeneration}/>}>
            {displayError && (
                <div className="mb-6 flex items-start gap-2 rounded-lg bg-destructive/10 px-4 py-3 ring-1 ring-destructive/20">
                    <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive"/>
                    <p className="text-sm break-words text-destructive">{displayError}</p>
                </div>
            )}

            {isRunning && (
                <div className="mb-6 flex items-start gap-2 rounded-lg border bg-muted/30 px-4 py-3">
                    <Loader2 className="mt-0.5 size-4 shrink-0 animate-spin text-muted-foreground"/>
                    <p className="text-sm text-muted-foreground">
                        {run?.progress?.step || 'Aktualisierung läuft...'} Die Beobachtungen werden beim Abruf
                        mitgelesen und erscheinen hier automatisch.
                    </p>
                </div>
            )}

            {isLoading ? (
                <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed px-3 py-12 text-sm text-muted-foreground">
                    <Loader2 className="size-5 animate-spin"/>
                    Lade Beobachtungen...
                </div>
            ) : saisons.length === 0 ? (
                <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed px-3 py-12 text-center">
                    <span className="grid size-14 place-items-center rounded-2xl border border-dashed bg-muted/30">
                        <ClipboardCheck className="size-6 text-muted-foreground"/>
                    </span>
                    <p className="text-sm font-medium">Noch keine Beobachtungen</p>
                    <p className="max-w-xs text-sm text-muted-foreground">
                        Sie werden beim nächsten Abruf aus DFBnet mitgeladen – über den Button oben
                        oder automatisch in der Nacht.
                    </p>
                </div>
            ) : (
                <div className="space-y-4">
                    <div className="flex flex-wrap gap-1.5">
                        {saisons.map((saison) => (
                            <Button
                                key={saison}
                                variant="ghost"
                                size="sm"
                                onClick={() => setGewaehlt(saison)}
                                className={cn(
                                    'text-muted-foreground',
                                    gewaehlt === saison &&
                                        'bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary'
                                )}
                            >
                                {saison}
                                <span className="ml-1 text-xs opacity-70">({anzahlJeSaison.get(saison) ?? 0})</span>
                            </Button>
                        ))}
                    </div>

                    <BeobachtungsKarte
                        titel="Herren"
                        untertitel="Schiri-Beobachtung"
                        beobachtungen={herren}
                        gelesen={herrenGelesen || herren.length > 0}
                        mitSpielklassen
                    />

                    {portal.map((gruppe) => (
                        <BeobachtungsKarte
                            key={gruppe.staffel}
                            titel={gruppe.staffel}
                            untertitel="Schiri-Portal"
                            beobachtungen={gruppe.beobachtungen}
                            gelesen
                        />
                    ))}
                </div>
            )}
        </AppShell>
    );
}
