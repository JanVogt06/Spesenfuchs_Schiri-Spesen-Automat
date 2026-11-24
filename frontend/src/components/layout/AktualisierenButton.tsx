import {Button} from '@/components/ui/button';
import {Loader2, RefreshCw} from 'lucide-react';
import type {ScrapeRun} from '@/hooks/useScrapeRun';
import {formatStand, letzterStand} from '@/lib/stand';

interface AktualisierenButtonProps {
    /** The latest fetch - supplies the status next to the button */
    run: ScrapeRun | null;
    laeuft: boolean;
    onClick: () => void;
}

/**
 * Header action: re-reads everything from DFBnet - assignments, season,
 * master data, observations. Next to it is when that last succeeded.
 */
export function AktualisierenButton({run, laeuft, onClick}: AktualisierenButtonProps) {
    const stand = letzterStand(run);

    return (
        <div className="flex items-center gap-2.5">
            {stand && !laeuft && (
                <p
                    className="text-right text-[0.6875rem] leading-tight text-muted-foreground"
                    title={`Zuletzt aus DFBnet gelesen am ${stand.toLocaleString('de-DE', {dateStyle: 'medium', timeStyle: 'short'})}`}
                >
                    <span className="block">Stand</span>
                    <span className="block whitespace-nowrap">{formatStand(stand)}</span>
                </p>
            )}
            <Button onClick={onClick} disabled={laeuft} size="sm">
                {laeuft ? (
                    <>
                        <Loader2 className="size-4 animate-spin"/>
                        <span className="sr-only sm:not-sr-only">Aktualisiert...</span>
                    </>
                ) : (
                    <>
                        <RefreshCw className="size-4"/>
                        <span className="sr-only sm:not-sr-only">Aktualisieren</span>
                    </>
                )}
            </Button>
        </div>
    );
}
