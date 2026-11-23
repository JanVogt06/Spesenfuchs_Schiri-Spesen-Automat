import {useEffect, useState} from 'react';
import {DFB_STATUS_EVENT, getCurrentUser} from '@/lib/auth';

/**
 * Seit wann DFBnet die gespeicherten Zugangsdaten ablehnt - oder null.
 *
 * Laedt beim Oeffnen einer Seite, nach jedem fertigen Abruf, nach dem
 * Speichern neuer Zugangsdaten und wenn die App wieder in den Vordergrund
 * kommt (eine installierte PWA bleibt oft tagelang offen, waehrend nachts
 * abgerufen wird).
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
                // Ohne Antwort lieber kein Hinweis als ein falscher
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
