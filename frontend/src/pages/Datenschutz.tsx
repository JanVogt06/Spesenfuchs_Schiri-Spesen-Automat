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
                            Deine eigenen Stammdaten aus DFBnet: Name, Anschrift, Geburtsdatum,
                            E-Mail-Adresse und Telefonnummern, Ausweisnummer und -gültigkeit,
                            Foto-Status, SR-Gebiet, Verein, Schiedsrichter-Status, Zusatzausbildungen,
                            Kreditor- und Debitor-Nummer sowie dein Qualifikations-Maximum. Sie werden
                            bei jedem Abruf mitgelesen und dienen allein der Anzeige im Reiter
                            „Stammdaten"; in keinem Dokument stehen sie. Die persönlichen Angaben
                            darunter liegen verschlüsselt (Fernet) in der Datenbank. Dein Passfoto
                            wird nicht abgerufen und nicht gespeichert.
                        </li>
                        <li>
                            Die zum jeweiligen Spiel angesetzten Unparteiischen mit Name, Anschrift,
                            Telefonnummer und E-Mail-Adresse, so wie DFBnet sie zum Zeitpunkt des Abrufs
                            ausweist. Diese Angaben stammen aus deiner Ansetzung und betreffen auch
                            Personen, die den Dienst selbst nicht nutzen. Name und Anschrift werden für
                            die Abrechnung benötigt, Telefon und E-Mail dienen ausschließlich der
                            Anzeige in deiner Spielübersicht und stehen in keinem Dokument.
                        </li>
                        <li>
                            Deine geleiteten Spiele aus DFBnet über alle dort angebotenen Saisons:
                            Datum, Liga, Paarung, Ergebnis, Karten je Mannschaft sowie das jeweilige
                            Gespann mit Namen und Rolle. Dazu die Einsatzbilanz je Saison und die
                            erfassten Lehrabende und Leistungsprüfungen. Die Namen der übrigen
                            Unparteiischen stammen aus der DFBnet-Statistik und betreffen auch
                            Personen, die den Dienst selbst nicht nutzen; gespeichert wird nur der
                            Name samt Rolle, keine Kontaktdaten. Diese Daten dienen allein der
                            Anzeige im Reiter „Saison" und stehen in keinem Dokument.
                        </li>
                        <li>Von dir eingetragene Kilometer und Kosten für öffentliche Verkehrsmittel</li>
                        <li>
                            Nutzungsprotokolle: Zeitpunkt jedes Logins, Zeitpunkt und Dateiname
                            jedes Downloads sowie Verlauf und Fehlermeldungen der DFBnet-Abrufe
                        </li>
                    </ul>
                    <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                        Erzeugte Abrechnungen werden nicht gespeichert. Sie entstehen bei jedem Download
                        neu aus den genannten Daten. Die Daten zu einem Spiel bleiben gespeichert, bis du
                        ihre Löschung verlangst oder deinen Account löschst. Die Saisondaten werden bei
                        jedem Abruf je Saison vollständig ersetzt und spiegeln damit immer den aktuellen
                        Stand in DFBnet.
                    </p>
                </>
            ),
        },
        {
            icon: Shield,
            title: 'Datensicherheit',
            content: (
                <p className="text-sm leading-relaxed text-muted-foreground">
                    Zugangsdaten und deine persönlichen Stammdaten werden verschlüsselt gespeichert,
                    Passwörter nur als Hash. Die Übertragung erfolgt ausschließlich über HTTPS. Deine
                    Daten werden nicht an Dritte weitergegeben und ausschließlich dafür verwendet, dir
                    deine Spesenabrechnungen und deine DFBnet-Daten im Browser bereitzustellen.
                    Spiel- und Stammdaten sind immer nur für den Account sichtbar, zu dem sie gehören.
                    Hinterlegst du andere DFBnet-Zugangsdaten, werden die gespeicherten Stamm- und
                    Saisondaten sofort gelöscht.
                </p>
            ),
        },
        {
            icon: null,
            title: 'Deine Rechte',
            content: (
                <p className="text-sm leading-relaxed text-muted-foreground">
                    Du hast jederzeit das Recht auf Auskunft, Berichtigung und Löschung deiner Daten.
                    Eine Selbstbedienungs-Funktion dafür gibt es derzeit nicht – schreib uns eine
                    E-Mail, dann löschen wir dein Konto und alle zugehörigen Daten von Hand,
                    einschließlich deiner Stammdaten, deiner Saisondaten und der zu deinen Spielen
                    gespeicherten Angaben zu Unparteiischen. Deine Stammdaten pflegst du in DFBnet; der Dienst spiegelt sie
                    nur und schreibt nichts nach DFBnet zurück.
                    Wer als Unparteiischer in einer Ansetzung auftaucht, ohne den Dienst selbst zu
                    nutzen, kann die Löschung dieser Angaben ebenfalls per E-Mail verlangen.
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
                    Stand: September 2026</p>
            </main>
        </div>
    );
}
