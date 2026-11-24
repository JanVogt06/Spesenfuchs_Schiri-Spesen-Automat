import {useState} from 'react';
import {Button} from '@/components/ui/button';
import {Input} from '@/components/ui/input';
import {Label} from '@/components/ui/label';
import {Card, CardContent, CardDescription, CardHeader, CardTitle} from '@/components/ui/card';
import {api} from '@/lib/api';
import {Lock, Eye, EyeOff} from 'lucide-react';

export function ChangePasswordForm() {
    const [currentPassword, setCurrentPassword] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [showCurrentPassword, setShowCurrentPassword] = useState(false);
    const [showNewPassword, setShowNewPassword] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');
    const [isLoading, setIsLoading] = useState(false);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setSuccess('');

        // Client-side validation
        if (newPassword.length < 8) {
            setError('Neues Passwort muss mindestens 8 Zeichen lang sein');
            return;
        }

        if (newPassword !== confirmPassword) {
            setError('Die neuen Passwörter stimmen nicht überein');
            return;
        }

        if (currentPassword === newPassword) {
            setError('Neues Passwort muss sich vom aktuellen unterscheiden');
            return;
        }

        setIsLoading(true);

        try {
            await api.post('/api/auth/change-password', {
                current_password: currentPassword,
                new_password: newPassword,
            });

            setSuccess('Passwort erfolgreich geändert!');
            setCurrentPassword('');
            setNewPassword('');
            setConfirmPassword('');
        } catch (fehler: unknown) {
            const err = fehler as {
                response?: {status?: number; data?: {error?: {message?: string}; detail?: string}};
            };
            // Extract detailed error message
            const errorData = err.response?.data;
            let message = 'Unbekannter Fehler beim Ändern des Passworts';

            if (errorData?.error?.message) {
                message = errorData.error.message;
            } else if (errorData?.detail) {
                message = errorData.detail;
            } else if (err.response?.status === 401) {
                message = 'Aktuelles Passwort ist falsch';
            } else if (err.response?.status === 400) {
                message = 'Ungültige Eingabe - bitte überprüfe deine Angaben';
            } else if (err.response?.status === 422) {
                message = 'Validierungsfehler - Passwort muss mindestens 8 Zeichen haben';
            } else if (!err.response) {
                message = 'Server nicht erreichbar - bitte versuche es später erneut';
            }

            setError(message);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <Card className="w-full">
            <CardHeader className="px-4 sm:px-6">
                <CardTitle className="text-base sm:text-lg flex items-center gap-2">
                    <Lock className="size-4"/>
                    Passwort ändern
                </CardTitle>
                <CardDescription className="text-sm">
                    Ändere dein Anmelde-Passwort für die App
                </CardDescription>
            </CardHeader>
            <CardContent className="px-4 sm:px-6">
                <form onSubmit={handleSubmit} className="space-y-4">
                    {/* Current password */}
                    <div className="space-y-2">
                        <Label htmlFor="currentPassword" className="text-sm sm:text-base">
                            Aktuelles Passwort
                        </Label>
                        <div className="relative">
                            <Input
                                id="currentPassword"
                                type={showCurrentPassword ? 'text' : 'password'}
                                value={currentPassword}
                                onChange={(e) => setCurrentPassword(e.target.value)}
                                required
                                placeholder="••••••••"
                                className="text-sm sm:text-base pr-10"
                            />
                            <button
                                type="button"
                                onClick={() => setShowCurrentPassword(!showCurrentPassword)}
                                aria-label={showCurrentPassword ? 'Aktuelles Passwort verbergen' : 'Aktuelles Passwort anzeigen'}
                                aria-pressed={showCurrentPassword}
                                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-muted-foreground"
                            >
                                {showCurrentPassword ? (
                                    <EyeOff className="h-4 w-4"/>
                                ) : (
                                    <Eye className="h-4 w-4"/>
                                )}
                            </button>
                        </div>
                    </div>

                    {/* New password */}
                    <div className="space-y-2">
                        <Label htmlFor="newPassword" className="text-sm sm:text-base">
                            Neues Passwort
                        </Label>
                        <div className="relative">
                            <Input
                                id="newPassword"
                                type={showNewPassword ? 'text' : 'password'}
                                value={newPassword}
                                onChange={(e) => setNewPassword(e.target.value)}
                                required
                                placeholder="Mindestens 8 Zeichen"
                                className="text-sm sm:text-base pr-10"
                            />
                            <button
                                type="button"
                                onClick={() => setShowNewPassword(!showNewPassword)}
                                aria-label={showNewPassword ? 'Neues Passwort verbergen' : 'Neues Passwort anzeigen'}
                                aria-pressed={showNewPassword}
                                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-muted-foreground"
                            >
                                {showNewPassword ? (
                                    <EyeOff className="h-4 w-4"/>
                                ) : (
                                    <Eye className="h-4 w-4"/>
                                )}
                            </button>
                        </div>
                    </div>

                    {/* Confirm password */}
                    <div className="space-y-2">
                        <Label htmlFor="confirmPassword" className="text-sm sm:text-base">
                            Neues Passwort bestätigen
                        </Label>
                        <Input
                            id="confirmPassword"
                            type="password"
                            value={confirmPassword}
                            onChange={(e) => setConfirmPassword(e.target.value)}
                            required
                            placeholder="••••••••"
                            className="text-sm sm:text-base"
                        />
                    </div>

                    {/* Error display */}
                    {error && (
                        <div className="rounded-lg bg-destructive/10 px-3 py-2 ring-1 ring-destructive/20">
                            <p className="text-sm break-words text-destructive">{error}</p>
                        </div>
                    )}

                    {/* Success display */}
                    {success && (
                        <div className="rounded-lg bg-success/10 px-3 py-2 ring-1 ring-success/20">
                            <p className="text-sm break-words text-success">✓ {success}</p>
                        </div>
                    )}

                    <Button type="submit" className="w-full text-sm sm:text-base" disabled={isLoading}>
                        {isLoading ? 'Wird geändert...' : 'Passwort ändern'}
                    </Button>
                </form>
            </CardContent>
        </Card>
    );
}