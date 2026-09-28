import {useState} from 'react';
import {Button} from '@/components/ui/button';
import {Card, CardContent, CardDescription, CardHeader, CardTitle} from '@/components/ui/card';
import {useInstallation} from '@/lib/pwa';
import {Smartphone, Share, SquarePlus, Download, X, CheckCircle2} from 'lucide-react';

const AUSGEBLENDET_KEY = 'installHinweisAusgeblendet';

/** Die drei Handgriffe in Safari - einen Button dafuer laesst Apple nicht zu */
function IosSchritte() {
    return (
        <ol className="space-y-1.5 text-sm text-muted-foreground">
            <li className="flex items-start gap-2">
                <span className="w-4 shrink-0 text-center font-medium text-foreground">1.</span>
                {/* Seit iOS 26 steckt "Teilen" in Safari hinter dem Drei-Punkte-Menue */}
                <span>
                    Auf <Share className="inline size-4 align-text-bottom text-foreground"/> „Teilen“
                    tippen, in neueren Safari-Versionen zuerst auf „•••“
                </span>
            </li>
            <li className="flex items-start gap-2">
                <span className="w-4 shrink-0 text-center font-medium text-foreground">2.</span>
                <span>
                    <SquarePlus className="mr-1 inline size-4 align-text-bottom text-foreground"/>
                    „Zum Home-Bildschirm“ wählen
                </span>
            </li>
            <li className="flex items-start gap-2">
                <span className="w-4 shrink-0 text-center font-medium text-foreground">3.</span>
                Mit „Hinzufügen“ bestätigen
            </li>
        </ol>
    );
}

/** Karte in den Einstellungen - erklaert den Weg auf jedem Geraet */
export function InstallCard() {
    const {installiert, kannInstallieren, ios, installieren} = useInstallation();

    return (
        <Card className="w-full">
            <CardHeader className="px-4 sm:px-6">
                <CardTitle className="flex items-center gap-2 text-base sm:text-lg">
                    <Smartphone className="size-4"/>
                    Als App installieren
                </CardTitle>
                <CardDescription className="text-sm">
                    Spesenfuchs mit eigenem Symbol auf dem Homescreen, ohne Browserleiste
                </CardDescription>
            </CardHeader>
            <CardContent className="px-4 sm:px-6">
                {installiert ? (
                    <p className="flex items-center gap-2 text-sm text-muted-foreground">
                        <CheckCircle2 className="size-4 shrink-0 text-primary"/>
                        Spesenfuchs ist auf diesem Gerät installiert.
                    </p>
                ) : kannInstallieren ? (
                    <Button onClick={installieren}>
                        <Download className="size-4"/>
                        App installieren
                    </Button>
                ) : ios ? (
                    <IosSchritte/>
                ) : (
                    <p className="text-sm text-muted-foreground">
                        Dein Browser bietet die Installation gerade nicht an. In Chrome und Edge findest du
                        sie im Browsermenü oder als Symbol in der Adressleiste, auf dem iPhone in Safari
                        über „Teilen“.
                    </p>
                )}
                <p className="mt-4 text-xs text-muted-foreground">
                    Updates kommen automatisch, du musst nichts nachinstallieren.
                </p>
            </CardContent>
        </Card>
    );
}

function istAusgeblendet(): boolean {
    try {
        return localStorage.getItem(AUSGEBLENDET_KEY) === '1';
    } catch {
        return false;
    }
}

/**
 * Hinweis auf dem Dashboard, nur auf Touch-Geraeten und nur, solange es etwas
 * zu tun gibt. Weggeklickt bleibt er weg - in den Einstellungen steht derselbe
 * Weg dauerhaft.
 */
export function InstallBanner() {
    const {installiert, kannInstallieren, ios, installieren} = useInstallation();
    const [ausgeblendet, setAusgeblendet] = useState(istAusgeblendet);
    const touch = window.matchMedia('(pointer: coarse)').matches;

    if (installiert || ausgeblendet || !touch || !(kannInstallieren || ios)) return null;

    const ausblenden = () => {
        setAusgeblendet(true);
        try {
            localStorage.setItem(AUSGEBLENDET_KEY, '1');
        } catch {
            // Ohne Speicher erscheint der Hinweis beim naechsten Laden eben wieder
        }
    };

    return (
        <div className="mb-6 flex items-start gap-3 rounded-lg border bg-primary/5 px-4 py-3">
            <Smartphone className="mt-0.5 size-4 shrink-0 text-primary"/>
            <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">Spesenfuchs als App</p>
                {kannInstallieren ? (
                    <>
                        <p className="mt-0.5 text-sm text-muted-foreground">
                            Mit eigenem Symbol auf dem Homescreen, ohne Browserleiste.
                        </p>
                        <Button size="sm" className="mt-2" onClick={installieren}>
                            <Download className="size-4"/>
                            App installieren
                        </Button>
                    </>
                ) : (
                    <div className="mt-1.5">
                        <IosSchritte/>
                    </div>
                )}
            </div>
            <Button
                variant="ghost"
                size="icon-sm"
                onClick={ausblenden}
                className="-mt-1 -mr-2 text-muted-foreground"
                aria-label="Hinweis ausblenden"
            >
                <X className="size-4"/>
            </Button>
        </div>
    );
}
