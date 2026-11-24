import {api} from './api';

export interface BugReportStatus {
    /** Whether mail can be sent at all on this server */
    verfuegbar: boolean;
    empfaenger: string;
}

export interface BugReport {
    titel: string;
    beschreibung: string;
    bereich: string;
    schritte: string;
}

/** Whether an outbox is set up - the form asks first */
export async function getBugReportStatus(): Promise<BugReportStatus> {
    const response = await api.get<BugReportStatus>('/api/bugreport/status');
    return response.data;
}

/** Sends a bug report to the configured address */
export async function sendeBugReport(bericht: BugReport): Promise<void> {
    await api.post('/api/bugreport', bericht);
}
