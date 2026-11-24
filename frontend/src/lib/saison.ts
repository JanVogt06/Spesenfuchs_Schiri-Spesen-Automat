import {api} from './api';
import type {SpielberichtKurz} from './spielberichte';

/** A person on the crew of a refereed match */
export interface SaisonGespann {
    rolle: string;
    name: string;
    ist_selbst: boolean;
}

/** A refereed match from the DFBnet tab "Spiele & Statistiken" */
export interface SaisonSpiel {
    id: number;
    saison: string;
    datum: string;
    uhrzeit: string;
    liga: string;
    heim: string;
    gast: string;
    ergebnis: string;
    /** null if DFBnet has recorded nothing for this match */
    heim_gelb: number | null;
    heim_gelbrot: number | null;
    heim_rot: number | null;
    gast_gelb: number | null;
    gast_gelbrot: number | null;
    gast_rot: number | null;
    eigene_rolle: string;
    gespann: SaisonGespann[];
    /** The assigned match report from DFBnet, if already read */
    spielbericht?: SpielberichtKurz | null;
}

/** A row of the appearance balance (SR, SRA 1, ..., total) */
export interface SaisonEinsatz {
    rolle: string;
    geleitet: string;
    zurueckgegeben: string;
    nicht_angetreten: string;
}

export interface SaisonLehrgaenge {
    lehrabend: string;
    lehrabend_online: string;
    leistungspruefung: string;
    scraped_at?: string;
}

export interface SaisonDetails {
    saison: string;
    spiele: SaisonSpiel[];
    einsaetze: SaisonEinsatz[];
    lehrgaenge: SaisonLehrgaenge | null;
}

/** Overview row per stored season */
export interface SaisonUebersicht {
    saison: string;
    spiele: number;
    letztes_spiel: string;
    scraped_at: string;
}

/** All seasons for which something is stored - newest first */
export async function getSaisons(): Promise<SaisonUebersicht[]> {
    const response = await api.get<SaisonUebersicht[]>('/api/saison');
    return response.data;
}

/**
 * A season with all matches, appearance balance and courses.
 *
 * The name is deliberately NOT encoded: seasons are called "26/27" at DFBnet, and
 * the endpoint accepts the slash as part of the path.
 */
export async function getSaison(saison: string): Promise<SaisonDetails> {
    const response = await api.get<SaisonDetails>(`/api/saison/${saison}`);
    return response.data;
}

/** "-" for values not recorded, otherwise the number */
export function formatKarte(wert: number | null): string {
    return wert === null || wert === undefined ? '–' : String(wert);
}

/** Sums a card column over all matches; null counts as 0 */
export function summeKarten(spiele: SaisonSpiel[], feld: keyof SaisonSpiel): number {
    return spiele.reduce((summe, spiel) => {
        const wert = spiel[feld];
        return summe + (typeof wert === 'number' ? wert : 0);
    }, 0);
}
