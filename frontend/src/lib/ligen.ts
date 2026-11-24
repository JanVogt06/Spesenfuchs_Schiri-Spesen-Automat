import {api} from './api';

/** A row of a league table */
export interface Tabellenplatz {
    platz: number;
    mannschaft: string;
    team_id: string;
    spiele: number;
    siege: number;
    unentschieden: number;
    niederlagen: number;
    tore: number;
    gegentore: number;
    punkte: number;
}

/** A league group together with its table */
export interface Staffel {
    staffel_id: string;
    anzeigename: string;
    spielklasse: string;
    verband: string;
    /** Rank of the league class, smaller is higher */
    rang: number;
    aktualisiert_at: string;
    mannschaften: number;
    tabelle: Tabellenplatz[];
}

export interface LigenBestand {
    staffeln: number;
    mannschaften: number;
    aktualisiert_at: string | null;
}

export interface LigenAntwort {
    bestand: LigenBestand;
    staffeln: Staffel[];
}

/** All reconciled league tables, highest league class first */
export async function getLigen(): Promise<LigenAntwort> {
    const response = await api.get<LigenAntwort>('/api/ligen');
    return response.data;
}

/** Goal difference, with a sign as in printed tables */
export function tordifferenz(platz: Tabellenplatz): string {
    const differenz = platz.tore - platz.gegentore;
    return differenz > 0 ? `+${differenz}` : String(differenz);
}
