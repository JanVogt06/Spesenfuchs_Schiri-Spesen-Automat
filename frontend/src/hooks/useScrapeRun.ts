import {useState, useEffect, useCallback, useRef} from 'react';
import {api} from '@/lib/api';

export interface ScrapeProgress {
    current: number;
    total: number;
    step: string;
    error_code?: string | null;
    error_message?: string | null;
}

export interface ScrapeRun {
    run_id?: number;
    status: 'idle' | 'pending' | 'scraping' | 'generating' | 'completed' | 'failed';
    matches_found?: number | null;
    started_at?: string;
    finished_at?: string | null;
    progress: ScrapeProgress | null;
}

const RUNNING_STATUS = ['pending', 'scraping', 'generating'];

export function isRunActive(run: ScrapeRun | null): boolean {
    return !!run && RUNNING_STATUS.includes(run.status);
}

/**
 * Verfolgt den aktuellen Scrape-Lauf des Users.
 *
 * Ersetzt useSessions/useSessionPolling: es gibt keine Session-Objekte mehr,
 * sondern genau einen Lauf-Zustand aus der Datenbank. Sobald ein Lauf fertig
 * ist, wird einmalig onFinished aufgerufen, damit die Spiele neu geladen
 * werden.
 */
export function useScrapeRun(onFinished?: () => void) {
    const [run, setRun] = useState<ScrapeRun | null>(null);
    const [isStarting, setIsStarting] = useState(false);
    const [error, setError] = useState('');

    // Ohne Ref wuerde jede neue Callback-Identitaet das Polling neu aufsetzen
    const onFinishedRef = useRef(onFinished);
    onFinishedRef.current = onFinished;
    const warRunning = useRef(false);

    const loadStatus = useCallback(async () => {
        try {
            const response = await api.get<ScrapeRun>('/api/scrape/status');
            const aktuell = response.data;
            setRun(aktuell);

            // Flanke von "laeuft" nach "fertig": genau einmal nachladen
            const laeuft = RUNNING_STATUS.includes(aktuell.status);
            if (warRunning.current && !laeuft) {
                onFinishedRef.current?.();
            }
            warRunning.current = laeuft;

            return aktuell;
        } catch (err) {
            console.error('Status konnte nicht geladen werden:', err);
            return null;
        }
    }, []);

    useEffect(() => {
        loadStatus();
    }, [loadStatus]);

    // Nur pollen, solange wirklich etwas laeuft
    useEffect(() => {
        if (!isRunActive(run)) return;

        const timer = setInterval(loadStatus, 2000);
        return () => clearInterval(timer);
    }, [run, loadStatus]);

    const startGeneration = useCallback(async () => {
        setIsStarting(true);
        setError('');
        try {
            await api.post('/api/generate', {});
            await loadStatus();
            warRunning.current = true;
        } catch (err: unknown) {
            const detail = (err as { response?: { data?: { error?: { message?: string } } } })
                ?.response?.data?.error?.message;
            setError(detail || 'Die Generierung konnte nicht gestartet werden.');
        } finally {
            setIsStarting(false);
        }
    }, [loadStatus]);

    return {
        run,
        isRunning: isRunActive(run),
        isStarting,
        error,
        startGeneration,
        reload: loadStatus,
    };
}
