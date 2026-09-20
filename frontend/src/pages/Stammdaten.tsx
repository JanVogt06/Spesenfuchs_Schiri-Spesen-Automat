import {useState, useEffect, useCallback} from 'react';
import {AppShell} from '@/components/layout/AppShell';
import {GenerateButton} from '@/components/matches/GenerateButton';
import {StammdatenCard} from '@/components/stammdaten/StammdatenCard';
import {useScrapeRun} from '@/hooks/useScrapeRun';
import {getStammdaten, type Stammdaten} from '@/lib/stammdaten';
import {AlertCircle, Loader2, IdCard} from 'lucide-react';

export function StammdatenPage() {
    const [daten, setDaten] = useState<Stammdaten | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [ladeFehler, setLadeFehler] = useState('');

    const loadStammdaten = useCallback(async () => {
        try {
            setDaten(await getStammdaten());
            setLadeFehler('');
        } catch (err: unknown) {
            const detail = (err as {response?: {data?: {error?: {message?: string}}}})
                ?.response?.data?.error?.message;
            setLadeFehler(detail || 'Die Stammdaten konnten nicht geladen werden.');
        } finally {
            setIsLoading(false);
        }
    }, []);

    // Die Stammdaten werden beim regulaeren Abruf mitgelesen, also haengt diese
    // Seite am selben Lauf wie das Dashboard und laedt nach, sobald er durch ist
    const {run, isRunning, isStarting, error, startGeneration} = useScrapeRun(loadStammdaten);

    useEffect(() => {
        loadStammdaten();
    }, [loadStammdaten]);

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
                        {run?.progress?.step || 'Aktualisierung läuft...'} Die Stammdaten werden am Ende
                        des Abrufs mitgelesen und erscheinen hier automatisch.
                    </p>
                </div>
            )}

            {isLoading ? (
                <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed px-3 py-12 text-sm text-muted-foreground">
                    <Loader2 className="size-5 animate-spin"/>
                    Lade Stammdaten...
                </div>
            ) : daten ? (
                <StammdatenCard daten={daten}/>
            ) : (
                <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed px-3 py-12 text-center">
                    <span className="grid size-14 place-items-center rounded-2xl border border-dashed bg-muted/30">
                        <IdCard className="size-6 text-muted-foreground"/>
                    </span>
                    <p className="text-sm font-medium">Noch keine Stammdaten</p>
                    <p className="max-w-xs text-sm text-muted-foreground">
                        Sie werden beim nächsten Abruf aus DFBnet mitgeladen - über den Button oben
                        oder automatisch in der Nacht.
                    </p>
                </div>
            )}
        </AppShell>
    );
}
