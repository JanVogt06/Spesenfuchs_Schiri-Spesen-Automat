import {api} from './api';

export interface StatistikMonat {
    /** "2026-09" */
    monat: string;
    spiele: number;
    spesen: number;
    fahrt_erfasst: number;
    fahrt_geschaetzt: number;
}

export interface Statistik {
    saisons: string[];
    /** The evaluated season - without data for the requested one, the newest */
    saison: string | null;
    /** dfbnet: DFBnet's list of officiated matches; ansetzungen: fallback without that list */
    quelle: 'dfbnet' | 'ansetzungen';
    spiele: number;
    ohne_rolle: number;
    ohne_satz: number;
    /** Officiated, but no appointment stored (before the first fetch): rate computed from the league */
    ohne_ansetzung: number;
    spesen: number;
    fahrtkosten: {
        erfasst: number;
        erfasst_spiele: number;
        geschaetzt: number;
        geschaetzt_spiele: number;
        geschaetzt_km: number;
        ohne_schaetzung: number;
        luftlinie_spiele: number;
    };
    gesamt: number;
    monate: StatistikMonat[];
    rollen: {rolle: string; spiele: number; spesen: number}[];
    /** Addresses or routes that are still being looked up */
    offen: number;
}

/** Without a season the server picks the newest one that has matches */
export async function getStatistik(saison: string | null): Promise<Statistik> {
    const response = await api.get<Statistik>('/api/statistik', saison ? {params: {saison}} : undefined);
    return response.data;
}

/** "2026-09" -> "Sep. 2026" */
export function monatsName(monat: string): string {
    const [jahr, nummer] = monat.split('-').map(Number);
    if (!jahr || !nummer) return monat;
    return new Date(jahr, nummer - 1, 1).toLocaleDateString('de-DE', {month: 'short', year: 'numeric'});
}
