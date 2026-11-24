import {api} from './api';
import type {SpielberichtKurz} from './spielberichte';

// Match data types - based on the actual DFBnet structure
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
    // Metadata from the backend
    _id: number;
    _datum?: string;
    _filename?: string;
    _expenses?: MatchExpenses | null;
    /** Set when a future assignment no longer appears in DFBnet */
    _missing_since?: string | null;
    /** The match report from DFBnet, once the match is over and the report has been read */
    _spielbericht?: SpielberichtKurz | null;
}

export interface SaveExpensesResult {
    success: boolean;
    filename: string;
    expenses: MatchExpenses | null;
}

/**
 * Saves travel costs/public transport costs (ÖVM) for a match.
 *
 * Nothing is regenerated any more: documents are only created on download
 * and then carry the stored value automatically.
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

/** A person or the venue at a point on the map */
export interface GeoEintrag {
    rolle: string;
    name: string;
}

export interface GeoPunkt {
    typ: 'spielstaette' | 'person';
    adresse: string;
    lat: number;
    lon: number;
    /** 'ort' means: only the centre of the town, the exact address could not be found */
    genauigkeit: 'adresse' | 'ort';
    /** Several if two assigned officials live at the same address */
    eintraege: GeoEintrag[];
}

export interface GeoDaten {
    punkte: GeoPunkt[];
    ohne_treffer: { rolle: string; name: string; adresse: string }[];
    /** The geocoder did not respond - trying again may work */
    gestoert: boolean;
    kacheln: { url: string; attribution: string };
}

/**
 * Coordinates of a match's addresses for the map.
 *
 * The first call for a match can take a few seconds: the addresses
 * are then looked up once at the geocoder. After that the server
 * answers from its cache.
 */
export async function getMatchGeo(matchId: number): Promise<GeoDaten> {
    const response = await api.get<GeoDaten>(`/api/matches/${matchId}/geo`);
    return response.data;
}

/** Form prefix of a role: sr, sra1, sra2 */
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

/** Kilometre suggestions for a match, each round trip in whole km */
export interface FahrtVorschlaege {
    /** strasse: route planner; luftlinie: fallback without a route planner; gestoert: address search unavailable */
    quelle: 'strasse' | 'luftlinie' | 'gestoert';
    selbst: RollenPraefix | null;
    einzeln: {km: Partial<Record<RollenPraefix, number>>; gesamt: number};
    fahrgemeinschaften: Fahrgemeinschaft[];
    ohne_anschrift: string[];
    ohne_spielort: boolean;
}

/** The first time, this queries the address search and route planner - that can take seconds */
export async function getFahrtVorschlaege(matchId: number): Promise<FahrtVorschlaege> {
    const response = await api.get<FahrtVorschlaege>(`/api/matches/${matchId}/fahrten`);
    return response.data;
}

// API functions
export async function getAllMatches(): Promise<MatchData[]> {
    const response = await api.get<MatchData[]>('/api/matches');
    return response.data;
}

/** Downloads the statement of a match - freshly generated on the server */
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

/** Downloads several selected matches bundled as a ZIP */
export async function downloadMatchesAsZip(
    matchIds: number[],
    fileFormat: 'docx' | 'pdf' | 'both' = 'both'
): Promise<void> {
    const response = await api.post(
        '/api/matches/download',
        {match_ids: matchIds, file_format: fileFormat},
        {responseType: 'blob'},
    );
    // Local date: toISOString would be UTC, i.e. yesterday shortly after midnight
    const jetzt = new Date();
    const datum = [
        jetzt.getFullYear(),
        String(jetzt.getMonth() + 1).padStart(2, '0'),
        String(jetzt.getDate()).padStart(2, '0'),
    ].join('-');
    triggerBrowserDownload(response.data, `Spesen_${datum}.zip`);
}

/**
 * Reads the server's error message from a failed request.
 *
 * Downloads use responseType 'blob', so axios also returns the JSON error
 * body as a Blob - accessing error.response.data.error directly would
 * yield undefined. The blob has to be read asynchronously first.
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