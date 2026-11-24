import type {ScrapeRun} from '@/hooks/useScrapeRun';

function gleicherTag(a: Date, b: Date): boolean {
    return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

/**
 * When data was last read successfully from DFBnet - at night or by button.
 * An aborted or running run has no state; null if there is
 * none or the timestamp is unusable.
 */
export function letzterStand(run: ScrapeRun | null): Date | null {
    if (run?.status !== 'completed' || !run.finished_at) return null;
    const zeitpunkt = new Date(run.finished_at);
    return Number.isNaN(zeitpunkt.getTime()) ? null : zeitpunkt;
}

/** "heute, 03:00", "gestern, 03:00", "22.11., 03:00" or with the year if it is not the current one */
export function formatStand(zeitpunkt: Date, jetzt: Date = new Date()): string {
    const uhrzeit = zeitpunkt.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'});
    const gestern = new Date(jetzt.getFullYear(), jetzt.getMonth(), jetzt.getDate() - 1);

    if (gleicherTag(zeitpunkt, jetzt)) return `heute, ${uhrzeit}`;
    if (gleicherTag(zeitpunkt, gestern)) return `gestern, ${uhrzeit}`;

    const datum = zeitpunkt.getFullYear() === jetzt.getFullYear()
        ? zeitpunkt.toLocaleDateString('de-DE', {day: '2-digit', month: '2-digit'})
        : zeitpunkt.toLocaleDateString('de-DE', {day: '2-digit', month: '2-digit', year: 'numeric'});
    return `${datum}, ${uhrzeit}`;
}
