import {api} from './api';

export interface BugReportStatus {
    /** Ob auf diesem Server überhaupt Post verschickt werden kann */
    verfuegbar: boolean;
    empfaenger: string;
}

export interface BugReport {
    titel: string;
    beschreibung: string;
    bereich: string;
    schritte: string;
}

/** Ob ein Postausgang eingerichtet ist - das Formular fragt vorher */
export async function getBugReportStatus(): Promise<BugReportStatus> {
    const response = await api.get<BugReportStatus>('/api/bugreport/status');
    return response.data;
}

/** Schickt einen Fehlerbericht an die hinterlegte Adresse */
export async function sendeBugReport(bericht: BugReport): Promise<void> {
    await api.post('/api/bugreport', bericht);
}
