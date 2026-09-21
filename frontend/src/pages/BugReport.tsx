import {useState, useEffect} from 'react';
import {Button} from '@/components/ui/button';
import {Input} from '@/components/ui/input';
import {Label} from '@/components/ui/label';
import {AppShell} from '@/components/layout/AppShell';
import {getBugReportStatus, sendeBugReport, type BugReportStatus} from '@/lib/bugreport';
import {AlertCircle, Bug, CheckCircle2, Loader2, Send} from 'lucide-react';

const BEREICHE = ['Dashboard', 'Spesen', 'Saison', 'Ligen', 'Stammdaten', 'Einstellungen', 'Sonstiges'];

function fehlertext(err: unknown, fallback: string): string {
    const detail = (err as {response?: {data?: {error?: {message?: string}}}})
        ?.response?.data?.error?.message;
    return detail || fallback;
}

export function BugReportPage() {
    const [status, setStatus] = useState<BugReportStatus | null>(null);
    const [titel, setTitel] = useState('');
    const [bereich, setBereich] = useState('');
    const [beschreibung, setBeschreibung] = useState('');
    const [schritte, setSchritte] = useState('');
    const [isSending, setIsSending] = useState(false);
    const [fehler, setFehler] = useState('');
    const [gesendet, setGesendet] = useState(false);

    useEffect(() => {
        getBugReportStatus()
            .then(setStatus)
            .catch(() => setStatus({verfuegbar: false, empfaenger: ''}));
    }, []);

    const absendbar = titel.trim().length > 0 && beschreibung.trim().length > 0 && !isSending;

    async function absenden(event: React.FormEvent) {
        event.preventDefault();
        if (!absendbar) return;

        setIsSending(true);
        setFehler('');

        try {
            await sendeBugReport({titel, beschreibung, bereich, schritte});
            setGesendet(true);
            setTitel('');
            setBereich('');
            setBeschreibung('');
            setSchritte('');
        } catch (err: unknown) {
            setFehler(fehlertext(err, 'Der Fehlerbericht konnte nicht gesendet werden.'));
        } finally {
            setIsSending(false);
        }
    }

    return (
        <AppShell>
            <div className="mx-auto w-full max-w-2xl space-y-6">
                <div>
                    <h1 className="text-lg font-semibold tracking-tight">Fehler melden</h1>
                    <p className="text-sm text-muted-foreground">
                        Etwas stimmt nicht? Dieser Bericht geht direkt an die Entwicklung
                        {status?.empfaenger ? ` (${status.empfaenger})` : ''}. Die eigene
                        Mailadresse wird als Absender mitgeschickt, damit eine Rückfrage möglich ist.
                    </p>
                </div>

                {status && !status.verfuegbar && (
                    <div className="flex items-start gap-2 rounded-lg bg-destructive/10 px-4 py-3 ring-1 ring-destructive/20">
                        <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive"/>
                        <p className="text-sm text-destructive">
                            Auf diesem Server ist kein Postausgang eingerichtet, Berichte können
                            deshalb nicht versendet werden. Nötig sind SMTP_HOST, SMTP_USER und
                            SMTP_PASSWORD in <code className="font-mono">data/.env</code>.
                        </p>
                    </div>
                )}

                {gesendet && (
                    <div className="flex items-start gap-2 rounded-lg bg-primary/10 px-4 py-3 ring-1 ring-primary/20">
                        <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-primary"/>
                        <p className="text-sm">
                            Danke – der Bericht ist unterwegs. Für einen weiteren einfach das
                            Formular erneut ausfüllen.
                        </p>
                    </div>
                )}

                {fehler && (
                    <div className="flex items-start gap-2 rounded-lg bg-destructive/10 px-4 py-3 ring-1 ring-destructive/20">
                        <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive"/>
                        <p className="text-sm break-words text-destructive">{fehler}</p>
                    </div>
                )}

                <form onSubmit={absenden} className="space-y-4 rounded-lg border p-4 sm:p-6">
                    <div className="space-y-2">
                        <Label htmlFor="titel">Worum geht es? *</Label>
                        <Input
                            id="titel"
                            value={titel}
                            onChange={(e) => setTitel(e.target.value)}
                            onFocus={() => setGesendet(false)}
                            placeholder="Kurz in einem Satz"
                            maxLength={150}
                            required
                        />
                    </div>

                    <div className="space-y-2">
                        <Label htmlFor="bereich">Wo in der Anwendung?</Label>
                        <select
                            id="bereich"
                            value={bereich}
                            onChange={(e) => setBereich(e.target.value)}
                            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
                        >
                            <option value="">Keine Angabe</option>
                            {BEREICHE.map((eintrag) => (
                                <option key={eintrag} value={eintrag}>{eintrag}</option>
                            ))}
                        </select>
                    </div>

                    <div className="space-y-2">
                        <Label htmlFor="beschreibung">Was ist passiert? *</Label>
                        <textarea
                            id="beschreibung"
                            value={beschreibung}
                            onChange={(e) => setBeschreibung(e.target.value)}
                            onFocus={() => setGesendet(false)}
                            rows={5}
                            maxLength={5000}
                            required
                            placeholder="Was war zu sehen, und was wäre zu erwarten gewesen?"
                            className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
                        />
                    </div>

                    <div className="space-y-2">
                        <Label htmlFor="schritte">Wie lässt es sich nachstellen?</Label>
                        <textarea
                            id="schritte"
                            value={schritte}
                            onChange={(e) => setSchritte(e.target.value)}
                            rows={4}
                            maxLength={5000}
                            placeholder="Betroffenes Spiel, angeklickte Schaltflächen, Reihenfolge …"
                            className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
                        />
                    </div>

                    <div className="flex items-center gap-3">
                        <Button type="submit" disabled={!absendbar || (status ? !status.verfuegbar : false)}>
                            {isSending ? <Loader2 className="size-4 animate-spin"/> : <Send className="size-4"/>}
                            Bericht senden
                        </Button>
                        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                            <Bug className="size-3.5"/>
                            Felder mit * sind nötig
                        </span>
                    </div>
                </form>
            </div>
        </AppShell>
    );
}
