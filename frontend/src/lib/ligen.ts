import {api} from './api';

/** Eine Zeile einer Ligatabelle */
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

/** Eine Staffel samt ihrer Tabelle */
export interface Staffel {
    staffel_id: string;
    anzeigename: string;
    spielklasse: string;
    verband: string;
    /** Rangfolge der Spielklasse, kleiner ist höher */
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

/** Alle abgeglichenen Ligatabellen, höchste Spielklasse zuerst */
export async function getLigen(): Promise<LigenAntwort> {
    const response = await api.get<LigenAntwort>('/api/ligen');
    return response.data;
}

/** Tordifferenz, mit Vorzeichen wie in gedruckten Tabellen */
export function tordifferenz(platz: Tabellenplatz): string {
    const differenz = platz.tore - platz.gegentore;
    return differenz > 0 ? `+${differenz}` : String(differenz);
}
