import {api} from './api';

// Match Data Types - basierend auf tatsächlicher DFBnet-Struktur
export interface SpielInfo {
    anpfiff?: string;
    heim_team?: string;
    gast_team?: string;
    mannschaftsart?: string;
    spielklasse?: string;
    staffel?: string;
    spieltag?: string;

    [key: string]: any;
}

export interface Schiedsrichter {
    rolle?: string;
    name?: string;
    telefon?: string;
    email?: string;
    strasse?: string;
    plz_ort?: string;

    [key: string]: any;
}

export interface Spielstaette {
    name?: string;
    adresse?: string;
    platz_typ?: string;

    [key: string]: any;
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
    const datum = new Date().toISOString().slice(0, 10);
    triggerBrowserDownload(response.data, `Spesen_${datum}.zip`);
}

function triggerBrowserDownload(blob: Blob, filename: string): void {
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
}