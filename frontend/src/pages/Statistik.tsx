import {useCallback, useState} from 'react';
import {Button} from '@/components/ui/button';
import {AppShell} from '@/components/layout/AppShell';
import {AktualisierenButton} from '@/components/layout/AktualisierenButton';
import {SpesenStatistik} from '@/components/statistik/SpesenStatistik';
import {SpielstaettenKarte} from '@/components/statistik/SpielstaettenKarte';
import {useScrapeRun} from '@/hooks/useScrapeRun';
import type {Statistik} from '@/lib/statistik';
import {AlertCircle} from 'lucide-react';
import {cn} from '@/lib/utils';

/**
 * Own expenses and travel costs per season, and the map of every venue the
 * user has officiated at. Both used to sit at the bottom of the "Saison" tab,
 * where nobody found them.
 */
export function StatistikPage() {
    // null: the newest season with matches - the server decides
    const [gewaehlt, setGewaehlt] = useState<string | null>(null);
    const [saisons, setSaisons] = useState<string[]>([]);
    const [angezeigt, setAngezeigt] = useState<string | null>(null);
    // After a fetch from DFBnet both cards load again from scratch
    const [stand, setStand] = useState(0);

    const geladen = useCallback((statistik: Statistik) => {
        setSaisons(statistik.saisons);
        setAngezeigt(statistik.saison);
    }, []);
    const neuLaden = useCallback(() => setStand((s) => s + 1), []);
    const {run, isRunning, isStarting, error, startGeneration} = useScrapeRun(neuLaden);

    return (
        <AppShell
            titel="Statistik"
            beschreibung="Deine Spesen und Fahrtkosten je Saison und alle Plätze, an denen du schon im Einsatz warst."
            actions={<AktualisierenButton run={run} laeuft={isStarting || isRunning} onClick={startGeneration}/>}
        >
            {error && (
                <div className="mb-6 flex items-start gap-2 rounded-lg bg-destructive/10 px-4 py-3 ring-1 ring-destructive/20">
                    <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive"/>
                    <p className="text-sm break-words text-destructive">{error}</p>
                </div>
            )}

            <div className="space-y-4">
                {saisons.length > 1 && (
                    <div role="group" aria-label="Saison" className="flex flex-wrap gap-1.5">
                        {saisons.map((saison) => (
                            <Button
                                key={saison}
                                variant="ghost"
                                size="sm"
                                aria-pressed={angezeigt === saison}
                                onClick={() => setGewaehlt(saison)}
                                className={cn(
                                    'text-muted-foreground',
                                    angezeigt === saison && 'bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary'
                                )}
                            >
                                {saison}
                            </Button>
                        ))}
                    </div>
                )}

                <SpesenStatistik key={`${gewaehlt ?? 'neueste'}#${stand}`} saison={gewaehlt} onGeladen={geladen}/>
                <SpielstaettenKarte key={stand} saison={angezeigt}/>
            </div>
        </AppShell>
    );
}
