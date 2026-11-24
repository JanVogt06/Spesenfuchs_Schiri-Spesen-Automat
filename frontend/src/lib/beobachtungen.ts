import {api} from './api';

/**
 * From which DFBnet module an observation comes:
 * - herren: referee observation (state association, men's leagues)
 * - portal: referee portal (DFB youth) - only few referees have these
 */
export type BeobachtungsQuelle = 'herren' | 'portal';

/** The own role on the crew in which the grade was given */
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
    /** The grade as DFBnet displays it */
    note_text: string;
    beobachter: string;
    freigegeben_am: string;
}

/** A completely read season of a source - even an empty one */
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
 * The groups for which a separate average is formed. SRA1 and SRA2 count
 * together as assistant.
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

/** One average per role group - only for groups with at least one grade */
export function schnitte(beobachtungen: Beobachtung[]): Schnitt[] {
    return ROLLEN_GRUPPEN.flatMap(({gruppe, label, rollen}) => {
        const noten = beobachtungen.filter((b) => rollen.includes(b.rolle)).map((b) => b.note);
        if (noten.length === 0) return [];
        const summe = noten.reduce((a, b) => a + b, 0);
        return [{gruppe, label, schnitt: summe / noten.length, anzahl: noten.length}];
    });
}

/** Grouped by league, in order of first appearance */
export function nachStaffel(beobachtungen: Beobachtung[]): {staffel: string; beobachtungen: Beobachtung[]}[] {
    const gruppen = new Map<string, Beobachtung[]>();
    for (const b of beobachtungen) {
        const staffel = b.staffel || 'Ohne Staffel';
        gruppen.set(staffel, [...(gruppen.get(staffel) ?? []), b]);
    }
    return [...gruppen].map(([staffel, liste]) => ({staffel, beobachtungen: liste}));
}

/** "25/26" -> 2025; unknown values sort to the end */
function startJahr(saison: string): number {
    const treffer = /^(\d{2})\/\d{2}$/.exec(saison.trim());
    return treffer ? 2000 + Number(treffer[1]) : -1;
}

/** Season of a date in DFBnet format: "26.01.2019" -> "18/19" (starts on 1 July) */
export function saisonVonDatum(deutsch: string | null): string | null {
    const treffer = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec((deutsch || '').trim());
    if (!treffer) return null;
    const jahr = Number(treffer[3]);
    const start = Number(treffer[2]) >= 7 ? jahr : jahr - 1;
    const kurz = (n: number) => String(n % 100).padStart(2, '0');
    return `${kurz(start)}/${kurz(start + 1)}`;
}

/**
 * The seasons that the tab offers, newest first.
 *
 * Men's: every read season from "Schiedsrichter seit" onwards - even without an
 * observation, because then that is exactly the answer. Portal: only seasons in
 * which there really are observations.
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
