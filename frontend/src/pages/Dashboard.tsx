import {useState, useEffect, useCallback} from 'react';
import {useNavigate} from 'react-router-dom';
import {Button} from '@/components/ui/button';
import {Card, CardContent, CardHeader, CardTitle} from '@/components/ui/card';
import {Separator} from '@/components/ui/separator';
import {AppShell} from '@/components/layout/AppShell';
import {GenerateButton} from '@/components/matches/GenerateButton';
import {MatchList} from '@/components/matches/MatchList';
import {useScrapeRun} from '@/hooks/useScrapeRun';
import {getAllMatches, type MatchData} from '@/lib/matches';
import {AlertCircle, Loader2} from 'lucide-react';
import {cn} from '@/lib/utils';

export function DashboardPage() {
    const navigate = useNavigate();
    const [matches, setMatches] = useState<MatchData[]>([]);
    const [isLoadingMatches, setIsLoadingMatches] = useState(true);
    const [matchesError, setMatchesError] = useState('');

    const loadMatches = useCallback(async () => {
        try {
            setMatches(await getAllMatches());
            setMatchesError('');
        } catch (err: unknown) {
            setMatchesError((err as Error).message);
        } finally {
            setIsLoadingMatches(false);
        }
    }, []);

    // Ein Lauf-Zustand statt einer Liste von Sessions; laedt die Spiele neu,
    // sobald der laufende Scrape durch ist
    const {run, isRunning, isStarting, error, startGeneration} = useScrapeRun(loadMatches);

    useEffect(() => {
        loadMatches();
    }, [loadMatches]);

    const displayError = error || matchesError;
    const istAnmeldefehler = run?.progress?.error_code === 'DFB_CREDENTIALS_INVALID';
    const fortschritt = run?.progress;

    return (
        <AppShell actions={<GenerateButton isGenerating={isStarting || isRunning} onClick={startGeneration}/>}>
            {displayError && (
                <div className="mb-6 flex items-start gap-2 rounded-lg bg-destructive/10 px-4 py-3 ring-1 ring-destructive/20 animate-in slide-in-from-top-2 duration-300">
                    <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive"/>
                    <p className="text-sm break-words text-destructive">{displayError}</p>
                </div>
            )}

            {isRunning && (
                <Card className="mb-6 gap-0 overflow-hidden py-0">
                    <CardHeader className="flex h-11 flex-row items-center gap-2 px-4 py-0">
                        <Loader2 className="size-4 animate-spin text-muted-foreground"/>
                        <CardTitle className="text-sm">Aktualisierung läuft</CardTitle>
                    </CardHeader>
                    <Separator/>
                    <CardContent className="space-y-4 p-4">
                        <p className="text-sm text-muted-foreground">
                            Die Spiele werden aus DFBnet geladen. Sie erscheinen automatisch, sobald es fertig ist.
                        </p>
                        <div className="space-y-1.5">
                            <div className="flex items-center justify-between text-xs">
                                <span className="text-muted-foreground">
                                    {fortschritt?.step || 'Initialisierung...'}
                                </span>
                                <span className="font-mono font-medium">
                                    {fortschritt && fortschritt.total > 0
                                        ? `${fortschritt.current}/${fortschritt.total}`
                                        : '…'}
                                </span>
                            </div>
                            <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                                <div
                                    className={cn(
                                        'h-full rounded-full bg-primary transition-all duration-500 ease-out',
                                        (!fortschritt || fortschritt.total === 0) && 'animate-pulse'
                                    )}
                                    style={{
                                        width: fortschritt && fortschritt.total > 0
                                            ? `${(fortschritt.current / fortschritt.total) * 100}%`
                                            : '5%'
                                    }}
                                />
                            </div>
                        </div>
                    </CardContent>
                </Card>
            )}

            {isLoadingMatches ? (
                <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed px-3 py-12 text-sm text-muted-foreground">
                    <Loader2 className="size-5 animate-spin"/>
                    Lade Spiele...
                </div>
            ) : (
                <div className="space-y-4">
                    {run?.status === 'failed' && (
                        <div className="flex items-start gap-3 rounded-lg bg-destructive/10 px-4 py-3 ring-1 ring-destructive/20">
                            <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive"/>
                            <div className="min-w-0 flex-1">
                                <p className="text-sm font-medium text-destructive">
                                    {istAnmeldefehler
                                        ? 'DFBnet-Login fehlgeschlagen'
                                        : 'Letzte Aktualisierung fehlgeschlagen'}
                                </p>
                                <p className="mt-0.5 text-sm text-destructive/80">
                                    {run.progress?.error_message || 'Bei der Aktualisierung ist ein Fehler aufgetreten.'}
                                </p>
                                {istAnmeldefehler && (
                                    <Button
                                        variant="destructive"
                                        size="sm"
                                        className="mt-2"
                                        onClick={() => navigate('/settings')}
                                    >
                                        Zugangsdaten prüfen
                                    </Button>
                                )}
                            </div>
                        </div>
                    )}

                    <MatchList matches={matches}/>
                </div>
            )}
        </AppShell>
    );
}
