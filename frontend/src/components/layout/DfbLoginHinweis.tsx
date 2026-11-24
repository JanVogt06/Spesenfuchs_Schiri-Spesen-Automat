import {useLocation, useNavigate} from 'react-router-dom';
import {KeyRound} from 'lucide-react';
import {Button} from '@/components/ui/button';

/** The anchor of the credentials card in the settings */
export const DFB_ZUGANG_ANKER = 'dfb-zugangsdaten';

function formatSeit(iso: string): string {
    const datum = new Date(iso);
    if (Number.isNaN(datum.getTime())) return '';
    return datum.toLocaleDateString('de-DE', {day: '2-digit', month: '2-digit', year: 'numeric'});
}

/**
 * Sits at the very top of every page while DFBnet rejects the stored
 * credentials. Without it this would only be noticed once assignments
 * are missing - DFBnet regularly demands a new password, and the
 * nightly fetch silently fails after that.
 */
export function DfbLoginHinweis({abgelehntSeit}: {abgelehntSeit: string}) {
    const navigate = useNavigate();
    const location = useLocation();
    const seit = formatSeit(abgelehntSeit);

    const zumFormular = () => {
        if (location.pathname === '/settings') {
            const karte = document.getElementById(DFB_ZUGANG_ANKER);
            karte?.scrollIntoView({behavior: 'smooth', block: 'center'});
            karte?.querySelector('input')?.focus({preventScroll: true});
        } else {
            navigate(`/settings#${DFB_ZUGANG_ANKER}`);
        }
    };

    return (
        <div
            role="alert"
            className="mb-6 flex flex-col gap-3 rounded-xl border border-destructive/40 bg-destructive/10 p-4 sm:flex-row sm:items-center sm:gap-4"
        >
            <span className="grid size-10 shrink-0 place-items-center rounded-full bg-destructive text-white">
                <KeyRound className="size-5"/>
            </span>
            <div className="min-w-0 flex-1">
                <p className="font-semibold text-destructive">
                    DFBnet lehnt deine Zugangsdaten ab
                </p>
                <p className="mt-0.5 text-sm break-words text-destructive/90">
                    {seit ? `Seit dem ${seit} ` : 'Zurzeit '}
                    schlägt die Anmeldung bei DFBnet fehl. Bis du die Zugangsdaten erneuerst, kommen keine
                    neuen Ansetzungen, Saisondaten oder Beobachtungen dazu. Meist hat DFBnet ein neues
                    Passwort verlangt.
                </p>
            </div>
            {/* Solid fill instead of the pale destructive variant: this is
                the one button to press here */}
            <Button
                className="shrink-0 bg-destructive text-white hover:bg-destructive/90 sm:self-center"
                onClick={zumFormular}
            >
                Zugangsdaten erneuern
            </Button>
        </div>
    );
}
