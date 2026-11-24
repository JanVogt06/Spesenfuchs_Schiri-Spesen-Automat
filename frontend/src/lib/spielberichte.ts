import {api} from './api';
import {triggerBrowserDownload} from './matches';

/** What the season and expense lists know of the report per match */
export interface SpielberichtKurz {
    id: number;
    /** Travel costs of the whole crew according to DFBnet, in euros */
    fahrtkosten: number | null;
    /** Referee/assistant expenses of the whole crew according to DFBnet, in euros */
    spesen: number | null;
    dokumente: number;
}

export type EreignisTyp =
    | 'tor' | 'eigentor' | 'elfmetertor' | 'elfmeterschiessen' | 'wechsel'
    | 'gelb' | 'gelbrot' | 'rot' | 'zeitstrafe' | 'unsportlichkeit' | string;

export interface Ereignis {
    minute: number | null;
    nachspielzeit: number | null;
    typ: EreignisTyp;
    seite: 'heim' | 'gast' | '';
    person: string;
    nummer: number | null;
    /** For team officials: coach, assistant coach, ... */
    funktion: string | null;
    grund: string;
    sonderbericht: boolean;
    /** Only for substitutions: the player who was substituted */
    person_raus?: string;
    nummer_raus?: number | null;
}

export interface Spieler {
    id: string;
    nummer: number | null;
    name: string;
    kapitaen: boolean;
    torwart: boolean;
    ersatz: boolean;
    status: string;
}

export interface Teamoffizieller {
    id: string;
    name: string;
    funktion: string;
}

export interface Aufstellung {
    spieler: Spieler[];
    offizielle: Teamoffizieller[];
}

export interface Zeitpunkt {
    name: string;
    zeit: string;
}

export interface SpielberichtDaten {
    spielkennung: string;
    heim: string;
    gast: string;
    runde: string;
    anstoss_geplant: string;
    beginn: string;
    ende: string;
    nachspielzeit: {h1: number | null; h2: number | null; v1: number | null; v2: number | null};
    spielstaette: {name: string; ort: string; strasse: string; belag: string};
    ergebnis: {
        halbzeit: string | null;
        regulaer: string | null;
        verlaengerung: string | null;
        endstand: string | null;
        wertung: string;
        abbruch_minute: number | null;
    };
    zuschauer: number | null;
    kosten: {fahrtkosten: number | null; spesen: number | null};
    gespann: {rolle: string; rolle_name: string; name: string; verein: string; nicht_angetreten: boolean}[];
    ereignisse: Ereignis[];
    aufstellung: {heim: Aufstellung; gast: Aufstellung};
    kontrollen: {name: string; wert: string; bemerkung: string}[];
    bemerkungen: string;
    fairplay: boolean;
    vorkommnisse: {
        gemeldet: boolean;
        gewalt: boolean | null;
        diskriminierung: boolean | null;
        spielabbruch: boolean | null;
        beschuldigte: string[];
        geschaedigte: string[];
    };
    bestaetigung: {heim: Zeitpunkt | null; gast: Zeitpunkt | null; schiedsrichter: Zeitpunkt | null};
}

export interface SpielberichtDokument {
    id: number;
    kategorie: string;
    dateiname: string;
    beschreibung: string;
    hochgeladen_von: string;
    hochgeladen_am: string;
    groesse: number;
}

export interface Spielbericht {
    id: number;
    saison: string;
    datum: string;
    uhrzeit: string;
    gruppe: string;
    spielnummer: string;
    spielkennung: string;
    heim: string;
    gast: string;
    ergebnis: string;
    fahrtkosten: number | null;
    spesen: number | null;
    scraped_at: string;
    daten: SpielberichtDaten;
    dokumente: SpielberichtDokument[];
}

/** From where a report was opened - ends up in the usage log */
export type BerichtQuelle = 'saison' | 'spesen';

/** Path of the detail page; the origin travels along as ?von= */
export function spielberichtPfad(id: number, von: BerichtQuelle): string {
    return `/spielbericht/${id}?von=${von}`;
}

export async function getSpielbericht(id: number, quelle?: string | null): Promise<Spielbericht> {
    const response = await api.get<Spielbericht>(`/api/spielberichte/${id}`, {
        params: quelle ? {quelle} : undefined,
    });
    return response.data;
}

export async function downloadDokument(berichtId: number, dokument: SpielberichtDokument): Promise<void> {
    const response = await api.get(`/api/spielberichte/${berichtId}/dokumente/${dokument.id}`, {
        responseType: 'blob',
        params: {aktion: 'laden'},
    });
    triggerBrowserDownload(response.data, dokument.dateiname);
}

/** Opens a PDF in a new tab instead of downloading it */
export async function oeffneDokument(berichtId: number, dokument: SpielberichtDokument): Promise<void> {
    // Open the window immediately: after the await it no longer counts as a click
    // by the user, and Safari then blocks it as a pop-up.
    const fenster = window.open('', '_blank');
    try {
        const response = await api.get(`/api/spielberichte/${berichtId}/dokumente/${dokument.id}`, {
            responseType: 'blob',
            params: {aktion: 'oeffnen'},
        });
        const url = window.URL.createObjectURL(response.data);
        if (fenster) {
            fenster.location.href = url;
        } else {
            triggerBrowserDownload(response.data, dokument.dateiname);
        }
        // The window still needs the URL for a while
        window.setTimeout(() => window.URL.revokeObjectURL(url), 60_000);
    } catch (err) {
        fenster?.close();
        throw err;
    }
}

export function formatEuro(wert: number | null | undefined): string {
    if (wert === null || wert === undefined) return '–';
    return wert.toLocaleString('de-DE', {style: 'currency', currency: 'EUR'});
}

/** "2026-11-22T13:30:00.000+01:00" -> "13:30" */
export function uhrzeitAus(iso: string): string {
    const treffer = /T(\d{2}:\d{2})/.exec(iso || '');
    return treffer ? treffer[1] : '';
}

/** "2026-11-22T18:00:12.000+01:00" -> "22.11.2026, 18:00" */
export function zeitpunktText(iso: string): string {
    const treffer = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}:\d{2}))?/.exec(iso || '');
    if (!treffer) return iso || '';
    return `${treffer[3]}.${treffer[2]}.${treffer[1]}${treffer[4] ? `, ${treffer[4]}` : ''}`;
}

export function minuteText(e: Pick<Ereignis, 'minute' | 'nachspielzeit'>): string {
    if (e.minute === null || e.minute === undefined) return '';
    return e.nachspielzeit ? `${e.minute}'+${e.nachspielzeit}` : `${e.minute}'`;
}

export const EREIGNIS_NAMEN: Record<string, string> = {
    tor: 'Tor',
    eigentor: 'Eigentor',
    elfmetertor: 'Elfmetertor',
    elfmeterschiessen: 'Elfmeterschießen',
    wechsel: 'Wechsel',
    gelb: 'Gelbe Karte',
    gelbrot: 'Gelb-Rote Karte',
    rot: 'Rote Karte',
    zeitstrafe: 'Zeitstrafe',
    unsportlichkeit: 'Unsportlichkeit',
};
