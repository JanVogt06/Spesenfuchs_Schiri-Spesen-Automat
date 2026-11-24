import {useEffect, useState} from 'react';
import {DFB_STATUS_EVENT, getCurrentUser} from '@/lib/auth';

/**
 * Since when DFBnet has rejected the stored credentials - or null.
 *
 * Loads when a page is opened, after every finished run, after
 * saving new credentials and when the app returns to the foreground
 * (an installed PWA often stays open for days while runs happen
 * at night).
 */
export function useDfbLoginStatus(): string | null {
    const [abgelehntSeit, setAbgelehntSeit] = useState<string | null>(null);

    useEffect(() => {
        let aktiv = true;

        const laden = () => {
            getCurrentUser()
                .then((user) => {
                    if (aktiv) setAbgelehntSeit(user.dfb_login_abgelehnt_seit ?? null);
                })
                // Better no notice than a wrong one when there is no response
                .catch(() => {});
        };
        const sichtbar = () => {
            if (document.visibilityState === 'visible') laden();
        };

        laden();
        window.addEventListener(DFB_STATUS_EVENT, laden);
        document.addEventListener('visibilitychange', sichtbar);
        return () => {
            aktiv = false;
            window.removeEventListener(DFB_STATUS_EVENT, laden);
            document.removeEventListener('visibilitychange', sichtbar);
        };
    }, []);

    return abgelehntSeit;
}
