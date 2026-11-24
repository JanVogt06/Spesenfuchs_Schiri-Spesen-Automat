import type {ScrapeRun} from '@/hooks/useScrapeRun';

function gleicherTag(a: Date, b: Date): boolean {
    return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

/**
 * Wann zuletzt erfolgreich aus DFBnet gelesen wurde - nachts oder per Knopf.
 * Ein abgebrochener oder laufender Abruf hat keinen Stand; null, wenn es
 * keinen gibt oder der Zeitstempel unbrauchbar ist.
 */
export function letzterStand(run: ScrapeRun | null): Date | null {
    if (run?.status !== 'completed' || !run.finished_at) return null;
    const zeitpunkt = new Date(run.finished_at);
    return Number.isNaN(zeitpunkt.getTime()) ? null : zeitpunkt;
}

/** "heute, 03:00", "gestern, 03:00", "22.11., 03:00" oder mit Jahr, wenn es nicht das laufende ist */
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
