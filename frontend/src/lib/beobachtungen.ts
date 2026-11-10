import {api} from './api';

/**
 * Aus welchem DFBnet-Modul eine Beobachtung stammt:
 * - herren: Schiri-Beobachtung (Landesverband, Herren-Spielklassen)
 * - portal: Schiri-Portal (DFB-Nachwuchs) - haben nur wenige Schiedsrichter
 */
export type BeobachtungsQuelle = 'herren' | 'portal';

/** Die eigene Rolle im Gespann, in der die Note vergeben wurde */
export type BeobachtungsRolle = 'SR' | 'SRA1' | 'SRA2' | '4OF';

export interface Beobachtung {
    id: number;
    quelle: BeobachtungsQuelle;
    saison: string;
    datum: string;
    uhrzeit: string;
    spieltag: string;
    staffel: string;
    heim: string;
    gast: string;
    ergebnis: string;
    rolle: BeobachtungsRolle;
    note: number;
    /** Die Note so, wie DFBnet sie anzeigt */
    note_text: string;
    beobachter: string;
    freigegeben_am: string;
}

/** Eine vollständig gelesene Saison einer Quelle - auch eine leere */
export interface GeleseneSaison {
    quelle: BeobachtungsQuelle;
    saison: string;
    anzahl: number;
    scraped_at: string;
}

export interface BeobachtungsDaten {
    schiedsrichter_seit: string | null;
    saisons: GeleseneSaison[];
    beobachtungen: Beobachtung[];
}

export async function getBeobachtungen(): Promise<BeobachtungsDaten> {
    const response = await api.get<BeobachtungsDaten>('/api/beobachtungen');
    return response.data;
}

/**
 * Die Gruppen, für die ein eigener Schnitt gebildet wird. SRA1 und SRA2 zählen
 * gemeinsam als Assistent.
 */
export type RollenGruppe = 'sr' | 'assistent' | 'vierter';

export const ROLLEN_GRUPPEN: {gruppe: RollenGruppe; label: string; rollen: BeobachtungsRolle[]}[] = [
    {gruppe: 'sr', label: 'Schiedsrichter', rollen: ['SR']},
    {gruppe: 'assistent', label: 'Assistent', rollen: ['SRA1', 'SRA2']},
    {gruppe: 'vierter', label: '4. Offizieller', rollen: ['4OF']},
];

export const ROLLEN_NAMEN: Record<BeobachtungsRolle, string> = {
    SR: 'SR',
    SRA1: 'SRA 1',
    SRA2: 'SRA 2',
    '4OF': '4. Offizieller',
};

export interface Schnitt {
    gruppe: RollenGruppe;
    label: string;
    schnitt: number;
    anzahl: number;
}

/** Ein Schnitt je Rollengruppe - nur für Gruppen mit mindestens einer Note */
export function schnitte(beobachtungen: Beobachtung[]): Schnitt[] {
    return ROLLEN_GRUPPEN.flatMap(({gruppe, label, rollen}) => {
        const noten = beobachtungen.filter((b) => rollen.includes(b.rolle)).map((b) => b.note);
        if (noten.length === 0) return [];
        const summe = noten.reduce((a, b) => a + b, 0);
        return [{gruppe, label, schnitt: summe / noten.length, anzahl: noten.length}];
    });
}

/** Gruppiert nach Staffel, in der Reihenfolge des ersten Auftretens */
export function nachStaffel(beobachtungen: Beobachtung[]): {staffel: string; beobachtungen: Beobachtung[]}[] {
    const gruppen = new Map<string, Beobachtung[]>();
    for (const b of beobachtungen) {
        const staffel = b.staffel || 'Ohne Staffel';
        gruppen.set(staffel, [...(gruppen.get(staffel) ?? []), b]);
    }
    return [...gruppen].map(([staffel, liste]) => ({staffel, beobachtungen: liste}));
}

/** "25/26" -> 2025; Unbekanntes sortiert ans Ende */
function startJahr(saison: string): number {
    const treffer = /^(\d{2})\/\d{2}$/.exec(saison.trim());
    return treffer ? 2000 + Number(treffer[1]) : -1;
}

/** Saison eines Datums im DFBnet-Format: "26.01.2019" -> "18/19" (Beginn am 1. Juli) */
export function saisonVonDatum(deutsch: string | null): string | null {
    const treffer = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec((deutsch || '').trim());
    if (!treffer) return null;
    const jahr = Number(treffer[3]);
    const start = Number(treffer[2]) >= 7 ? jahr : jahr - 1;
    const kurz = (n: number) => String(n % 100).padStart(2, '0');
    return `${kurz(start)}/${kurz(start + 1)}`;
}

/**
 * Die Saisons, die der Reiter anbietet, neueste zuerst.
 *
 * Herren: jede gelesene Saison ab "Schiedsrichter seit" - auch ohne
 * Beobachtung, denn dann ist genau das die Auskunft. Portal: nur Saisons, in
 * denen es dort wirklich Beobachtungen gibt.
 */
export function angeboteneSaisons(daten: BeobachtungsDaten): string[] {
    const erste = saisonVonDatum(daten.schiedsrichter_seit);
    const ab = erste ? startJahr(erste) : -Infinity;

    const saisons = new Set<string>();
    for (const s of daten.saisons) {
        if (s.quelle === 'herren' && startJahr(s.saison) >= ab) saisons.add(s.saison);
    }
    for (const b of daten.beobachtungen) saisons.add(b.saison);

    return [...saisons].sort((a, b) => startJahr(b) - startJahr(a));
}

const ZWEI_STELLEN = new Intl.NumberFormat('de-DE', {minimumFractionDigits: 2, maximumFractionDigits: 2});

/** 243.375 -> "243,38" */
export function formatSchnitt(wert: number): string {
    return ZWEI_STELLEN.format(wert);
}

/** "2026-09-20" -> "20.09.2026" */
export function formatDatum(iso: string): string {
    const teile = (iso || '').split('-');
    return teile.length === 3 ? `${teile[2]}.${teile[1]}.${teile[0]}` : iso;
}
