import {api} from './api';

/**
 * Die eigenen Stammdaten aus DFBnet.
 *
 * Alle Felder sind optional: der Scraper liefert nur, was er auf der Seite
 * findet, und alte Datensätze kennen neu hinzugekommene Felder noch nicht.
 * Die Index-Signatur sorgt dafür, dass ein Feld, das DFBnet später ergänzt,
 * bis in die Anzeige durchkommt, ohne dass dieser Typ nachgezogen werden muss.
 */
export interface Stammdaten {
    // Kontaktdaten
    name_vorname?: string;
    strasse?: string;
    plz_ort?: string;
    geburtsdatum?: string;
    email?: string;
    telefon_privat?: string;
    telefon_geschaeftlich?: string;
    telefon_mobil?: string;

    // Ausweis & Foto
    ausweisnummer?: string;
    ausweisgueltigkeit?: string;
    foto_status?: string;
    foto_gueltigkeit?: string;

    // Meldedaten und Status
    sr_gebiet?: string;
    schiedsrichter_seit?: string;
    verein?: string;
    fehlmonate?: string;
    zusatzausbildungen?: string;
    patensystem_am?: string;
    kreditor_nr?: string;
    debitor_nr?: string;
    status?: string;
    umsatzsteuerpflichtig?: string;
    fussball_de_hinweis?: string;
    bemerkung?: string;

    // Qualifikations-Maximum
    qmax_sr?: string;
    qmax_sra1?: string;
    qmax_sra2?: string;
    qmax_beobachter?: string;

    // Metadaten vom Backend
    user_id?: number;
    first_seen_at?: string;
    scraped_at?: string;

    [key: string]: unknown;
}

/**
 * Lädt die Stammdaten des angemeldeten Users.
 *
 * Vor dem ersten Abruf antwortet das Backend mit 200 und null - das ist ein
 * Leerzustand, kein Fehler.
 */
export async function getStammdaten(): Promise<Stammdaten | null> {
    const response = await api.get<Stammdaten | null>('/api/stammdaten');
    return response.data;
}
