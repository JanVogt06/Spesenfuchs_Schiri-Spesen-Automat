import {useState} from 'react';
import {useNavigate, Link} from 'react-router-dom';
import {Button} from '@/components/ui/button';
import {Input} from '@/components/ui/input';
import {Label} from '@/components/ui/label';
import {Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle} from '@/components/ui/card';
import {login} from '@/lib/auth';
import {AlertCircle} from 'lucide-react';

export function LoginForm() {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [isLoading, setIsLoading] = useState(false);

    const navigate = useNavigate();

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setIsLoading(true);

        try {
            await login(email, password);
            navigate('/dashboard');
        } catch (err: unknown) {
            const axiosError = err as {
                message?: string;
                response?: { data?: { error?: { message?: string } } };
            };
            // Ohne Antwort hat der API-Client schon "Keine Verbindung ..." eingesetzt
            const errorMessage = axiosError.response
                ? axiosError.response.data?.error?.message || 'Login fehlgeschlagen'
                : axiosError.message || 'Login fehlgeschlagen';
            setError(errorMessage);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <Card className="w-full max-w-md mx-4 sm:mx-0">
            <CardHeader className="px-4 sm:px-6">
                <CardTitle className="text-lg sm:text-xl">Anmelden</CardTitle>
                <CardDescription className="text-sm">
                    Melde dich mit deinem Spesenfuchs-Account an
                </CardDescription>
            </CardHeader>
            <CardContent className="px-4 sm:px-6">
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div className="space-y-2">
                        <Label htmlFor="email" className="text-sm sm:text-base">E-Mail</Label>
                        <Input
                            id="email"
                            type="email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            required
                            placeholder="deine@email.de"
                            className="text-sm sm:text-base"
                            autoComplete="email"
                        />
                    </div>

                    <div className="space-y-2">
                        <Label htmlFor="password" className="text-sm sm:text-base">Passwort</Label>
                        <Input
                            id="password"
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            required
                            placeholder="••••••••"
                            className="text-sm sm:text-base"
                            autoComplete="current-password"
                        />
                    </div>

                    {error && (
                        <div className="rounded-lg bg-destructive/10 px-3 py-2 ring-1 ring-destructive/20">
                            <div className="flex items-start gap-2">
                                <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive"/>
                                <p className="text-sm break-words text-destructive">
                                    {error}
                                </p>
                            </div>
                        </div>
                    )}

                    <Button
                        type="submit"
                        className="w-full text-sm sm:text-base"
                        disabled={isLoading}
                    >
                        {isLoading ? 'Anmelden...' : 'Anmelden'}
                    </Button>
                </form>
            </CardContent>
            <CardFooter className="flex justify-center px-4 sm:px-6">
                <p className="text-sm text-muted-foreground text-center">
                    Noch kein Account?{' '}
                    <Link to="/register" className="text-primary hover:underline">
                        Jetzt registrieren
                    </Link>
                </p>
            </CardFooter>
        </Card>
    );
}