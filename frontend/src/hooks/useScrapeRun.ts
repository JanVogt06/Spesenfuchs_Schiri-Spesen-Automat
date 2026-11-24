import {useState, useEffect, useCallback, useRef} from 'react';
import {api} from '@/lib/api';
import {meldeDfbStatusGeaendert} from '@/lib/auth';

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
 * Tracks the current scrape run of the user.
 *
 * Replaces useSessions/useSessionPolling: there are no session objects anymore,
 * just exactly one run state from the database. As soon as a run is finished,
 * onFinished is called once so that the matches
 * are reloaded.
 */
export function useScrapeRun(onFinished?: () => void) {
    const [run, setRun] = useState<ScrapeRun | null>(null);
    const [isStarting, setIsStarting] = useState(false);
    const [error, setError] = useState('');

    // Without a ref every new callback identity would restart the polling
    const onFinishedRef = useRef(onFinished);
    onFinishedRef.current = onFinished;
    const warRunning = useRef(false);

    const loadStatus = useCallback(async () => {
        try {
            const response = await api.get<ScrapeRun>('/api/scrape/status');
            const aktuell = response.data;
            setRun(aktuell);

            // Edge from "running" to "finished": reload exactly once
            const laeuft = RUNNING_STATUS.includes(aktuell.status);
            if (warRunning.current && !laeuft) {
                onFinishedRef.current?.();
                // The run has checked the credentials - accepted or rejected
                meldeDfbStatusGeaendert();
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

    // Only poll while something is actually running
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
            // Set before the first status: if the run is already over by then
            // (process failed immediately), loadStatus detects the edge this way
            // and calls onFinished - instead of it never or belatedly coming.
            warRunning.current = true;
            await loadStatus();
        } catch (err: unknown) {
            const detail = (err as { response?: { data?: { error?: { message?: string } } } })
                ?.response?.data?.error?.message;
            setError(detail || 'Die Aktualisierung konnte nicht gestartet werden.');
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
