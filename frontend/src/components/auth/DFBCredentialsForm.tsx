import {useState, useEffect, useRef} from 'react';
import {useLocation} from 'react-router-dom';
import {AlertCircle} from 'lucide-react';
import {Button} from '@/components/ui/button';
import {Input} from '@/components/ui/input';
import {Label} from '@/components/ui/label';
import {Card, CardContent, CardDescription, CardHeader, CardTitle} from '@/components/ui/card';
import {api} from '@/lib/api';
import {meldeDfbStatusGeaendert} from '@/lib/auth';
import {cn} from '@/lib/utils';
import {DFB_ZUGANG_ANKER} from '@/components/layout/DfbLoginHinweis';

export function DFBCredentialsForm() {
    const [dfbUsername, setDfbUsername] = useState('');
    const [dfbPassword, setDfbPassword] = useState('');
    const [hasCredentials, setHasCredentials] = useState(false);
    const [abgelehnt, setAbgelehnt] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');
    const [isLoading, setIsLoading] = useState(false);

    // Prüfe beim Laden ob Credentials bereits gespeichert sind
    useEffect(() => {
        const checkCredentials = async () => {
            try {
                const response = await api.get('/api/auth/dfb-credentials/status');
                setHasCredentials(response.data.has_credentials);
                setAbgelehnt(!!response.data.abgelehnt_seit);
            } catch (err) {
                console.error('Fehler beim Laden des Credential-Status:', err);
            }
        };
        checkCredentials();
    }, []);

    // Aus dem Hinweis oben kommend: direkt zur Karte und ins erste Feld
    const location = useLocation();
    const karteRef = useRef<HTMLDivElement>(null);
    useEffect(() => {
        if (location.hash !== `#${DFB_ZUGANG_ANKER}`) return;
        karteRef.current?.scrollIntoView({behavior: 'smooth', block: 'center'});
        karteRef.current?.querySelector('input')?.focus({preventScroll: true});
    }, [location.hash]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setSuccess('');
        setIsLoading(true);

        try {
            await api.post('/api/auth/dfb-credentials', {
                dfb_username: dfbUsername,
                dfb_password: dfbPassword,
            });

            setSuccess(abgelehnt
                ? 'Gespeichert. Ob DFBnet sie annimmt, zeigt der nächste Abruf – heute Nacht oder sofort über den Generieren-Knopf oben.'
                : 'DFB-Credentials erfolgreich gespeichert!');
            setHasCredentials(true);
            setAbgelehnt(false);
            setDfbUsername('');
            setDfbPassword('');
            meldeDfbStatusGeaendert();
        } catch (err: unknown) {
            const detail = (err as {response?: {data?: {error?: {message?: string}}}})
                ?.response?.data?.error?.message;
            setError(detail || 'Fehler beim Speichern');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <Card
            id={DFB_ZUGANG_ANKER}
            ref={karteRef}
            className={cn('w-full scroll-mt-24', abgelehnt && 'ring-2 ring-destructive')}
        >
            <CardHeader className="px-4 sm:px-6">
                <CardTitle className="text-base sm:text-lg">DFB-Zugangsdaten</CardTitle>
                <CardDescription className="text-sm">
                    Speichere deine DFBnet-Zugangsdaten für die automatische Generierung
                </CardDescription>
            </CardHeader>
            <CardContent className="px-4 sm:px-6">
                {hasCredentials && abgelehnt && (
                    <div className="mb-4 flex items-start gap-2 rounded-lg bg-destructive/10 px-3 py-2 ring-1 ring-destructive/20">
                        <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive"/>
                        <p className="text-sm text-destructive">
                            DFBnet lehnt die gespeicherten Zugangsdaten ab. Trag hier dein aktuelles
                            DFBnet-Passwort ein.
                        </p>
                    </div>
                )}

                {hasCredentials && !abgelehnt && (
                    <div className="mb-4 rounded-lg bg-success/10 px-3 py-2 ring-1 ring-success/20">
                        <p className="text-sm text-success">
                            ✓ DFB-Credentials sind gespeichert
                        </p>
                    </div>
                )}

                <form onSubmit={handleSubmit} className="space-y-4">
                    <div className="space-y-2">
                        <Label htmlFor="dfbUsername" className="text-sm sm:text-base">DFB-Benutzername</Label>
                        <Input
                            id="dfbUsername"
                            type="text"
                            value={dfbUsername}
                            onChange={(e) => setDfbUsername(e.target.value)}
                            required
                            placeholder="Dein DFBnet-Benutzername"
                            className="text-sm sm:text-base"
                        />
                    </div>

                    <div className="space-y-2">
                        <Label htmlFor="dfbPassword" className="text-sm sm:text-base">DFB-Passwort</Label>
                        <Input
                            id="dfbPassword"
                            type="password"
                            value={dfbPassword}
                            onChange={(e) => setDfbPassword(e.target.value)}
                            required
                            placeholder="••••••••"
                            className="text-sm sm:text-base"
                        />
                    </div>

                    {error && (
                        <div className="text-sm break-words text-destructive">
                            {error}
                        </div>
                    )}

                    {success && (
                        <div className="text-sm break-words text-success">
                            {success}
                        </div>
                    )}

                    <Button type="submit" className="w-full text-sm sm:text-base" disabled={isLoading}>
                        {isLoading ? 'Speichern...' : hasCredentials ? 'Aktualisieren' : 'Speichern'}
                    </Button>

                    <p className="text-xs text-muted-foreground break-words">
                        Deine Zugangsdaten werden verschlüsselt gespeichert.
                    </p>
                </form>
            </CardContent>
        </Card>
    );
}