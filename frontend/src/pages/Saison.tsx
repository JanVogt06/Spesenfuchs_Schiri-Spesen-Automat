import {useState, useEffect, useCallback} from 'react';
import {Button} from '@/components/ui/button';
import {AppShell} from '@/components/layout/AppShell';
import {GenerateButton} from '@/components/matches/GenerateButton';
import {SaisonBilanz} from '@/components/saison/SaisonBilanz';
import {SaisonSpiele} from '@/components/saison/SaisonSpiele';
import {useScrapeRun} from '@/hooks/useScrapeRun';
import {getSaisons, getSaison, type SaisonUebersicht, type SaisonDetails} from '@/lib/saison';
import {AlertCircle, Loader2, Trophy} from 'lucide-react';
import {cn} from '@/lib/utils';

function fehlertext(err: unknown, fallback: string): string {
    const detail = (err as {response?: {data?: {error?: {message?: string}}}})
        ?.response?.data?.error?.message;
    return detail || fallback;
}

export function SaisonPage() {
    const [saisons, setSaisons] = useState<SaisonUebersicht[]>([]);
    const [gewaehlt, setGewaehlt] = useState<string | null>(null);
    const [details, setDetails] = useState<SaisonDetails | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [isLoadingDetails, setIsLoadingDetails] = useState(false);
    const [ladeFehler, setLadeFehler] = useState('');

    const loadSaisons = useCallback(async () => {
        try {
            const liste = await getSaisons();
            setSaisons(liste);
            setLadeFehler('');

            // Beim ersten Laden die neueste Saison zeigen; nach einem Abruf die
            // gewaehlte beibehalten, solange es sie noch gibt.
            setGewaehlt((bisher) => {
                if (bisher && liste.some((s) => s.saison === bisher)) return bisher;
                return liste.length > 0 ? liste[0].saison : null;
            });
        } catch (err: unknown) {
            setLadeFehler(fehlertext(err, 'Die Saisons konnten nicht geladen werden.'));
        } finally {
            setIsLoading(false);
        }
    }, []);

    // Die Saisondaten werden beim regulaeren Abruf mitgelesen, die Seite haengt
    // also am selben Lauf wie das Dashboard
    const {run, isRunning, isStarting, error, startGeneration} = useScrapeRun(loadSaisons);

    useEffect(() => {
        loadSaisons();
    }, [loadSaisons]);

    useEffect(() => {
        if (!gewaehlt) {
            setDetails(null);
            return;
        }

        let abgebrochen = false;
        setIsLoadingDetails(true);

        getSaison(gewaehlt)
            .then((daten) => {
                // Ein schneller Klick auf eine andere Saison darf nicht von der
                // langsameren aelteren Antwort ueberschrieben werden.
                if (!abgebrochen) setDetails(daten);
            })
            .catch((err: unknown) => {
                if (!abgebrochen) setLadeFehler(fehlertext(err, 'Die Saison konnte nicht geladen werden.'));
            })
            .finally(() => {
                if (!abgebrochen) setIsLoadingDetails(false);
            });

        return () => {
            abgebrochen = true;
        };
    }, [gewaehlt]);

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
                        {run?.progress?.step || 'Aktualisierung läuft...'} Die Saisondaten werden am Ende
                        des Abrufs mitgelesen und erscheinen hier automatisch.
                    </p>
                </div>
            )}

            {isLoading ? (
                <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed px-3 py-12 text-sm text-muted-foreground">
                    <Loader2 className="size-5 animate-spin"/>
                    Lade Saisons...
                </div>
            ) : saisons.length === 0 ? (
                <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed px-3 py-12 text-center">
                    <span className="grid size-14 place-items-center rounded-2xl border border-dashed bg-muted/30">
                        <Trophy className="size-6 text-muted-foreground"/>
                    </span>
                    <p className="text-sm font-medium">Noch keine Saisondaten</p>
                    <p className="max-w-xs text-sm text-muted-foreground">
                        Sie werden beim nächsten Abruf aus DFBnet mitgeladen – über den Button oben
                        oder automatisch in der Nacht.
                    </p>
                </div>
            ) : (
                <div className="space-y-4">
                    <div className="flex flex-wrap gap-1.5">
                        {saisons.map((eintrag) => (
                            <Button
                                key={eintrag.saison}
                                variant="ghost"
                                size="sm"
                                onClick={() => setGewaehlt(eintrag.saison)}
                                className={cn(
                                    'text-muted-foreground',
                                    gewaehlt === eintrag.saison &&
                                        'bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary'
                                )}
                            >
                                {eintrag.saison}
                                <span className="ml-1 text-xs opacity-70">({eintrag.spiele})</span>
                            </Button>
                        ))}
                    </div>

                    {isLoadingDetails && !details ? (
                        <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed px-3 py-12 text-sm text-muted-foreground">
                            <Loader2 className="size-5 animate-spin"/>
                            Lade Saison...
                        </div>
                    ) : details ? (
                        <div className={cn('space-y-4', isLoadingDetails && 'opacity-60')}>
                            <SaisonBilanz einsaetze={details.einsaetze} lehrgaenge={details.lehrgaenge}/>
                            <SaisonSpiele spiele={details.spiele}/>
                        </div>
                    ) : null}
                </div>
            )}
        </AppShell>
    );
}
