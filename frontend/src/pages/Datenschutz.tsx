import {Button} from '@/components/ui/button';
import {Card, CardContent} from '@/components/ui/card';
import {useNavigate} from 'react-router-dom';
import {ArrowLeft, Shield, Server, Mail, Receipt} from 'lucide-react';

export function Datenschutz() {
    const navigate = useNavigate();

    const sections = [
        {
            icon: Mail,
            title: 'Verantwortlicher',
            content: (
                <p className="text-sm leading-relaxed text-muted-foreground">
                    Jan Vogt<br/>
                    E-Mail: <a href="mailto:spesen-generator@jan-vogt.dev" className="text-foreground underline underline-offset-4 hover:no-underline">spesen-generator@jan-vogt.dev</a>
                </p>
            ),
        },
        {
            icon: Server,
            title: 'Erhobene Daten',
            content: (
                <>
                    <p className="mb-2 text-sm leading-relaxed text-muted-foreground">
                        Wir speichern folgende Daten zur Bereitstellung des Dienstes:
                    </p>
                    <ul className="list-inside list-disc space-y-1 text-sm text-muted-foreground">
                        <li>Benutzername und Passwort (gehashed mit PBKDF2)</li>
                        <li>DFBnet-Zugangsdaten (verschlüsselt mit Fernet)</li>
                        <li>Aus DFBnet abgerufene Spieldaten: Paarung, Anstoß, Spielklasse und Spielstätte</li>
                        <li>
                            Die zum jeweiligen Spiel angesetzten Unparteiischen mit Name, Anschrift,
                            Telefonnummer und E-Mail-Adresse, so wie DFBnet sie zum Zeitpunkt des Abrufs
                            ausweist. Diese Angaben stammen aus deiner Ansetzung und betreffen auch
                            Personen, die den Dienst selbst nicht nutzen. Name und Anschrift werden für
                            die Abrechnung benötigt, Telefon und E-Mail dienen ausschließlich der
                            Anzeige in deiner Spielübersicht und stehen in keinem Dokument.
                        </li>
                        <li>Von dir eingetragene Kilometer und Kosten für öffentliche Verkehrsmittel</li>
                    </ul>
                    <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                        Erzeugte Abrechnungen werden nicht gespeichert. Sie entstehen bei jedem Download
                        neu aus den genannten Daten. Die Daten zu einem Spiel bleiben gespeichert, bis du
                        ihre Löschung verlangst oder deinen Account löschst.
                    </p>
                </>
            ),
        },
        {
            icon: Shield,
            title: 'Datensicherheit',
            content: (
                <p className="text-sm leading-relaxed text-muted-foreground">
                    Zugangsdaten werden verschlüsselt gespeichert, Passwörter nur als Hash. Die Übertragung
                    erfolgt ausschließlich über HTTPS. Deine Daten werden nicht an Dritte weitergegeben und
                    ausschließlich zur Erstellung deiner Spesenabrechnungen verwendet. Spieldaten sind
                    immer nur für den Account sichtbar, zu dessen Ansetzung sie gehören.
                </p>
            ),
        },
        {
            icon: null,
            title: 'Deine Rechte',
            content: (
                <p className="text-sm leading-relaxed text-muted-foreground">
                    Du hast jederzeit das Recht auf Auskunft, Berichtigung und Löschung deiner Daten.
                    Kontaktiere uns dazu einfach per E-Mail. Bei Löschung deines Accounts werden alle
                    zugehörigen Daten entfernt, einschließlich der zu deinen Spielen gespeicherten
                    Angaben zu Unparteiischen. Wer als Unparteiischer in einer Ansetzung auftaucht,
                    ohne den Dienst selbst zu nutzen, kann die Löschung dieser Angaben ebenfalls per
                    E-Mail verlangen.
                </p>
            ),
        },
    ];

    return (
        <div className="flex min-h-screen flex-col bg-background text-foreground">
            {/* Header */}
            <header className="sticky top-0 z-40 border-b bg-card">
                <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4 sm:px-6">
                    <button className="flex items-center gap-2.5" onClick={() => navigate('/')}>
                        <span className="grid size-7 place-items-center rounded-lg bg-primary text-primary-foreground">
                            <Receipt className="size-4"/>
                        </span>
                        <span className="text-sm font-semibold tracking-tight">Spesenfuchs</span>
                    </button>
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => navigate('/')}
                        className="text-muted-foreground"
                    >
                        <ArrowLeft className="size-4"/>
                        Zurück
                    </Button>
                </div>
            </header>

            {/* Content */}
            <main className="mx-auto w-full max-w-2xl flex-1 px-4 py-10 sm:px-6">
                <h1 className="mb-6 text-2xl font-semibold tracking-tight sm:text-3xl">
                    Datenschutzerklärung
                </h1>

                <div className="space-y-3">
                    {sections.map((section, index) => (
                        <Card key={index} className="py-5">
                            <CardContent className="px-5">
                                <div className="flex items-start gap-3">
                                    {section.icon && (
                                        <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-muted">
                                            <section.icon className="size-4 text-foreground"/>
                                        </span>
                                    )}
                                    <div className="min-w-0">
                                        <h2 className="mb-1.5 font-medium">{section.title}</h2>
                                        {section.content}
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    ))}
                </div>

                <p className="mt-8 text-center text-sm text-muted-foreground">
                    Stand: Januar 2025
                </p>
            </main>
        </div>
    );
}
