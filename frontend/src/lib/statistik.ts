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
    /** Die ausgewertete Saison - ohne Daten zur gefragten die neueste */
    saison: string | null;
    spiele: number;
    ohne_rolle: number;
    ohne_satz: number;
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
    /** Adressen oder Strecken, die noch nachgeschlagen werden */
    offen: number;
}

export async function getStatistik(saison: string): Promise<Statistik> {
    const response = await api.get<Statistik>('/api/statistik', {params: {saison}});
    return response.data;
}

/** "2026-09" -> "Sep. 2026" */
export function monatsName(monat: string): string {
    const [jahr, nummer] = monat.split('-').map(Number);
    if (!jahr || !nummer) return monat;
    return new Date(jahr, nummer - 1, 1).toLocaleDateString('de-DE', {month: 'short', year: 'numeric'});
}
