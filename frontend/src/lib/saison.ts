import {api} from './api';

/** Eine Person im Gespann eines geleiteten Spiels */
export interface SaisonGespann {
    rolle: string;
    name: string;
    ist_selbst: boolean;
}

/** Ein geleitetes Spiel aus dem DFBnet-Reiter "Spiele & Statistiken" */
export interface SaisonSpiel {
    id: number;
    saison: string;
    datum: string;
    uhrzeit: string;
    liga: string;
    heim: string;
    gast: string;
    ergebnis: string;
    /** null, wenn DFBnet zu diesem Spiel nichts erfasst hat */
    heim_gelb: number | null;
    heim_gelbrot: number | null;
    heim_rot: number | null;
    gast_gelb: number | null;
    gast_gelbrot: number | null;
    gast_rot: number | null;
    eigene_rolle: string;
    gespann: SaisonGespann[];
}

/** Eine Zeile der Einsatzbilanz (SR, SRA 1, ..., Summe) */
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

/** Übersichtszeile pro gespeicherter Saison */
export interface SaisonUebersicht {
    saison: string;
    spiele: number;
    letztes_spiel: string;
    scraped_at: string;
}

/** Alle Saisons, zu denen etwas gespeichert ist - neueste zuerst */
export async function getSaisons(): Promise<SaisonUebersicht[]> {
    const response = await api.get<SaisonUebersicht[]>('/api/saison');
    return response.data;
}

/**
 * Eine Saison mit allen Spielen, Einsatzbilanz und Lehrgängen.
 *
 * Der Name wird bewusst NICHT kodiert: Saisons heißen bei DFBnet "26/27", und
 * der Endpunkt nimmt den Schrägstrich als Teil des Pfades entgegen.
 */
export async function getSaison(saison: string): Promise<SaisonDetails> {
    const response = await api.get<SaisonDetails>(`/api/saison/${saison}`);
    return response.data;
}

/** "-" für nicht erfasste Werte, sonst die Zahl */
export function formatKarte(wert: number | null): string {
    return wert === null || wert === undefined ? '–' : String(wert);
}

/** Summiert eine Kartenspalte über alle Spiele; null zählt als 0 */
export function summeKarten(spiele: SaisonSpiel[], feld: keyof SaisonSpiel): number {
    return spiele.reduce((summe, spiel) => {
        const wert = spiel[feld];
        return summe + (typeof wert === 'number' ? wert : 0);
    }, 0);
}
