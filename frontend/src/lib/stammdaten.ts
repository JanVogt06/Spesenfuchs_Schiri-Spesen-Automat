import {api} from './api';

/**
 * The own master data from DFBnet.
 *
 * All fields are optional: the scraper delivers only what it
 * finds on the page, and old records do not yet know newly added fields.
 * The index signature ensures that a field that DFBnet adds later
 * makes it through to the display without this type having to be updated.
 */
export interface Stammdaten {
    // Contact data
    name_vorname?: string;
    strasse?: string;
    plz_ort?: string;
    geburtsdatum?: string;
    email?: string;
    telefon_privat?: string;
    telefon_geschaeftlich?: string;
    telefon_mobil?: string;

    // ID card & photo
    ausweisnummer?: string;
    ausweisgueltigkeit?: string;
    foto_status?: string;
    foto_gueltigkeit?: string;

    // Registration data and status
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

    // Qualification maximum
    qmax_sr?: string;
    qmax_sra1?: string;
    qmax_sra2?: string;
    qmax_beobachter?: string;

    // Metadata from the backend
    user_id?: number;
    first_seen_at?: string;
    scraped_at?: string;

    [key: string]: unknown;
}

/**
 * Loads the master data of the logged-in user.
 *
 * Before the first run the backend answers with 200 and null - that is an
 * empty state, not an error.
 */
export async function getStammdaten(): Promise<Stammdaten | null> {
    const response = await api.get<Stammdaten | null>('/api/stammdaten');
    return response.data;
}
