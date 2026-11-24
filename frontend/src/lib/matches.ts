import {api} from './api';
import type {SpielberichtKurz} from './spielberichte';

// Match Data Types - basierend auf tatsächlicher DFBnet-Struktur
export interface SpielInfo {
    anpfiff?: string;
    heim_team?: string;
    gast_team?: string;
    mannschaftsart?: string;
    spielklasse?: string;
    staffel?: string;
    spieltag?: string;

    [key: string]: unknown;
}

export interface Schiedsrichter {
    rolle?: string;
    name?: string;
    telefon?: string;
    email?: string;
    strasse?: string;
    plz_ort?: string;

    [key: string]: unknown;
}

export interface Spielstaette {
    name?: string;
    adresse?: string;
    platz_typ?: string;

    [key: string]: unknown;
}

export interface MatchExpenses {
    sr_km?: number | null;
    sr_oevm?: number | null;
    sra1_km?: number | null;
    sra1_oevm?: number | null;
    sra2_km?: number | null;
    sra2_oevm?: number | null;
}

export interface MatchData {
    spiel_info: SpielInfo;
    schiedsrichter: Schiedsrichter[];
    spielstaette: Spielstaette;
    // Metadata von Backend
    _id: number;
    _datum?: string;
    _filename?: string;
    _expenses?: MatchExpenses | null;
    /** Gesetzt, wenn eine künftige Ansetzung nicht mehr in DFBnet steht */
    _missing_since?: string | null;
    /** Der Spielbericht aus DFBnet, sobald das Spiel vorbei und der Bericht gelesen ist */
    _spielbericht?: SpielberichtKurz | null;
}

export interface SaveExpensesResult {
    success: boolean;
    filename: string;
    expenses: MatchExpenses | null;
}

/**
 * Speichert Fahrtkosten/ÖVM für ein Spiel.
 *
 * Es wird nichts mehr neu generiert: Dokumente entstehen erst beim Download
 * und tragen den gespeicherten Wert dann automatisch.
 */
export async function saveMatchExpenses(
    matchId: number,
    expenses: MatchExpenses
): Promise<SaveExpensesResult> {
    const response = await api.post<SaveExpensesResult>('/api/matches/expenses', {
        match_id: matchId,
        ...expenses,
    });
    return response.data;
}

/** Eine Person oder die Spielstätte an einem Punkt der Karte */
export interface GeoEintrag {
    rolle: string;
    name: string;
}

export interface GeoPunkt {
    typ: 'spielstaette' | 'person';
    adresse: string;
    lat: number;
    lon: number;
    /** 'ort' heißt: nur der Ortsmittelpunkt, die genaue Anschrift war nicht auffindbar */
    genauigkeit: 'adresse' | 'ort';
    /** Mehrere, wenn zwei Angesetzte unter derselben Anschrift wohnen */
    eintraege: GeoEintrag[];
}

export interface GeoDaten {
    punkte: GeoPunkt[];
    ohne_treffer: { rolle: string; name: string; adresse: string }[];
    /** Der Geocoder hat nicht geantwortet - ein erneuter Versuch kann klappen */
    gestoert: boolean;
    kacheln: { url: string; attribution: string };
}

/**
 * Koordinaten der Anschriften eines Spiels für die Karte.
 *
 * Der erste Aufruf zu einem Spiel kann ein paar Sekunden dauern: die
 * Adressen werden dann einmalig beim Geocoder nachgeschlagen. Danach
 * antwortet der Server aus seinem Zwischenspeicher.
 */
export async function getMatchGeo(matchId: number): Promise<GeoDaten> {
    const response = await api.get<GeoDaten>(`/api/matches/${matchId}/geo`);
    return response.data;
}

/** Formular-Praefix einer Rolle: sr, sra1, sra2 */
export type RollenPraefix = 'sr' | 'sra1' | 'sra2';

/** An approximate point on the driver's way where the others join */
export interface Treffpunkt {
    lat: number;
    lon: number;
    /** Village or town nearby, if the geocoder knew one */
    name: string | null;
}

export interface Fahrt {
    fahrer: RollenPraefix;
    /** In pick-up order; with a meeting point: the ones driving there */
    mitfahrer: RollenPraefix[];
    /** Kilometres of the driver, round trip */
    km: number;
    /** Set if the others drive to a meeting point instead of being picked up */
    treffpunkt: Treffpunkt | null;
    /** With a meeting point: each passenger's own kilometres there and back */
    zubringer?: Partial<Record<RollenPraefix, number>>;
}

export interface Fahrgemeinschaft {
    fahrten: Fahrt[];
    km: Partial<Record<RollenPraefix, number>>;
    gesamt: number;
    ersparnis: number;
}

/** Kilometer-Vorschläge eines Spiels, jeweils Hin- und Rückfahrt in ganzen km */
export interface FahrtVorschlaege {
    /** strasse: Routenplaner; luftlinie: Notbehelf ohne Routenplaner; gestoert: Adresssuche ausgefallen */
    quelle: 'strasse' | 'luftlinie' | 'gestoert';
    selbst: RollenPraefix | null;
    einzeln: {km: Partial<Record<RollenPraefix, number>>; gesamt: number};
    fahrgemeinschaften: Fahrgemeinschaft[];
    ohne_anschrift: string[];
    ohne_spielort: boolean;
}

/** Fragt beim ersten Mal Adresssuche und Routenplaner - das kann Sekunden dauern */
export async function getFahrtVorschlaege(matchId: number): Promise<FahrtVorschlaege> {
    const response = await api.get<FahrtVorschlaege>(`/api/matches/${matchId}/fahrten`);
    return response.data;
}

// API Funktionen
export async function getAllMatches(): Promise<MatchData[]> {
    const response = await api.get<MatchData[]>('/api/matches');
    return response.data;
}

/** Lädt die Abrechnung eines Spiels - wird serverseitig frisch erzeugt */
export async function downloadMatchDocument(
    matchId: number,
    fileFormat: 'docx' | 'pdf',
    filename: string
): Promise<void> {
    const response = await api.get(`/api/matches/${matchId}/download/${fileFormat}`, {
        responseType: 'blob',
    });
    triggerBrowserDownload(response.data, filename);
}

/** Lädt mehrere ausgewählte Spiele gebündelt als ZIP */
export async function downloadMatchesAsZip(
    matchIds: number[],
    fileFormat: 'docx' | 'pdf' | 'both' = 'both'
): Promise<void> {
    const response = await api.post(
        '/api/matches/download',
        {match_ids: matchIds, file_format: fileFormat},
        {responseType: 'blob'},
    );
    // Lokales Datum: toISOString waere UTC, kurz nach Mitternacht also gestern
    const jetzt = new Date();
    const datum = [
        jetzt.getFullYear(),
        String(jetzt.getMonth() + 1).padStart(2, '0'),
        String(jetzt.getDate()).padStart(2, '0'),
    ].join('-');
    triggerBrowserDownload(response.data, `Spesen_${datum}.zip`);
}

/**
 * Liest die Fehlermeldung des Servers aus einer fehlgeschlagenen Anfrage.
 *
 * Downloads laufen mit responseType 'blob', deshalb liefert axios auch den
 * JSON-Fehlerkörper als Blob - ein direkter Zugriff auf error.response.data.error
 * ergäbe undefined. Der Blob muss erst asynchron gelesen werden.
 */
export async function extractApiError(error: unknown, fallback: string): Promise<string> {
    const antwort = (error as {response?: {data?: unknown}})?.response?.data;
    if (!antwort) return fallback;

    try {
        const text = antwort instanceof Blob ? await antwort.text() : JSON.stringify(antwort);
        const geparst = JSON.parse(text);
        return geparst?.error?.message || geparst?.detail || fallback;
    } catch {
        return fallback;
    }
}

export function triggerBrowserDownload(blob: Blob, filename: string): void {
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
}