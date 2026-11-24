import {useMemo, useState} from 'react';
import type {MatchData} from '@/lib/matches';
import {downloadMatchDocument, downloadMatchesAsZip, extractApiError} from '@/lib/matches';
import {MatchCard} from '../matches/MatchCard';
import {Button} from '@/components/ui/button';
import {Input} from '@/components/ui/input';
import {heuteIso, nachMonat, passtZurSuche, teileSpiele} from '@/lib/spieleliste';
import {cn} from '@/lib/utils';
import {Calendar, Download, Search} from 'lucide-react';

type Ansicht = 'kommend' | 'vergangen';

interface MatchListProps {
    matches: MatchData[];
    /** Reloads the matches after travel costs have been saved */
    onReload?: () => void;
}

export function MatchList({matches, onReload}: MatchListProps) {
    // Key "<matchId>:<format>": PDFs are now only created on click and
    // take seconds, so several downloads can run at the same time.
    // A single shared state would reset the other one each time.
    const [laufendeDownloads, setLaufendeDownloads] = useState<string[]>([]);
    const [selectedIds, setSelectedIds] = useState<number[]>([]);
    const [isBulkDownloading, setIsBulkDownloading] = useState(false);
    const [bulkError, setBulkError] = useState('');
    const [suche, setSuche] = useState('');

    const heute = heuteIso();
    const {kommend, vergangen} = useMemo(
        () => teileSpiele(matches.filter((m) => passtZurSuche(m, suche)), heute),
        [matches, suche, heute],
    );
    // Until the first choice: without an upcoming assignment, go straight to the past matches
    const [gewaehlteAnsicht, setAnsicht] = useState<Ansicht | null>(null);
    const gibtKommende = useMemo(() => teileSpiele(matches, heute).kommend.length > 0, [matches, heute]);
    const ansicht: Ansicht = gewaehlteAnsicht ?? (gibtKommende ? 'kommend' : 'vergangen');
    const sichtbar = ansicht === 'kommend' ? kommend : vergangen;
    const gruppen = useMemo(() => nachMonat(sichtbar), [sichtbar]);

    // "Spiel 3" as a fallback title depends on the position in the whole list,
    // not on the one in the filtered list
    const position = useMemo(() => new Map(matches.map((m, i) => [m._id, i])), [matches]);

    const handleDownload = async (match: MatchData, fileFormat: 'docx' | 'pdf') => {
        // 'docx' means "the editable file" - for NOFV matches an Excel workbook
        const originalName = match._filename || `spiel_${match._id}.docx`;
        const filename = fileFormat === 'pdf' ? originalName.replace(/\.(docx|xlsx)$/i, '.pdf') : originalName;
        const key = `${match._id}:${fileFormat}`;

        setLaufendeDownloads(prev => [...prev, key]);
        setBulkError('');
        try {
            await downloadMatchDocument(match._id, fileFormat, filename);
        } catch (error) {
            console.error('Download failed:', error);
            setBulkError(await extractApiError(error, 'Download fehlgeschlagen.'));
        } finally {
            setLaufendeDownloads(prev => prev.filter(k => k !== key));
        }
    };

    const toggleSelected = (matchId: number) => {
        setSelectedIds(prev =>
            prev.includes(matchId) ? prev.filter(id => id !== matchId) : [...prev, matchId]
        );
    };

    const handleBulkDownload = async () => {
        setIsBulkDownloading(true);
        setBulkError('');
        try {
            await downloadMatchesAsZip(selectedIds, 'both');
            setSelectedIds([]);
        } catch (error) {
            console.error('Sammel-Download fehlgeschlagen:', error);
            setBulkError(await extractApiError(
                error, 'Sammel-Download fehlgeschlagen. Bitte erneut versuchen.'));
        } finally {
            setIsBulkDownloading(false);
        }
    };

    if (matches.length === 0) {
        return (
            <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed px-3 py-12 text-center">
                <span className="grid size-14 place-items-center rounded-2xl border border-dashed bg-muted/30">
                    <Calendar className="size-6 text-muted-foreground"/>
                </span>
                <p className="text-sm font-medium">Noch keine Spiele</p>
                <p className="max-w-xs text-sm text-muted-foreground">
                    Hol die Ansetzungen über „Aktualisieren“ oben – oder warte auf den automatischen Abruf in der Nacht.
                </p>
            </div>
        );
    }

    const reiter: {wert: Ansicht; label: string; anzahl: number}[] = [
        {wert: 'kommend', label: 'Kommend', anzahl: kommend.length},
        {wert: 'vergangen', label: 'Vergangen', anzahl: vergangen.length},
    ];

    return (
        <div className="space-y-3">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div role="group" aria-label="Zeitraum" className="inline-flex self-start rounded-lg border bg-card p-1">
                    {reiter.map((eintrag) => (
                        <button
                            key={eintrag.wert}
                            type="button"
                            aria-pressed={ansicht === eintrag.wert}
                            onClick={() => setAnsicht(eintrag.wert)}
                            className={cn(
                                'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                                ansicht === eintrag.wert
                                    ? 'bg-primary/10 text-primary'
                                    : 'text-muted-foreground hover:text-foreground'
                            )}
                        >
                            {eintrag.label}
                            <span className="ml-1.5 text-xs tabular-nums opacity-70">{eintrag.anzahl}</span>
                        </button>
                    ))}
                </div>

                <div className="relative sm:w-80">
                    <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"/>
                    <Input
                        type="search"
                        value={suche}
                        onChange={(e) => setSuche(e.target.value)}
                        placeholder="Verein, Spielklasse oder Spielstätte"
                        aria-label="Spiele durchsuchen"
                        className="pl-9"
                    />
                </div>
            </div>

            {selectedIds.length > 0 && (
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-muted/30 px-3 py-2">
                    <span className="text-sm">
                        {selectedIds.length} {selectedIds.length === 1 ? 'Spiel' : 'Spiele'} ausgewählt
                    </span>
                    <div className="flex items-center gap-2">
                        <Button variant="ghost" size="sm" onClick={() => setSelectedIds([])}>
                            Auswahl aufheben
                        </Button>
                        <Button size="sm" onClick={handleBulkDownload} disabled={isBulkDownloading}>
                            <Download className="size-3.5"/>
                            {isBulkDownloading ? 'Erstelle ZIP...' : 'Als ZIP laden'}
                        </Button>
                    </div>
                </div>
            )}

            {bulkError && (
                <p className="rounded-lg border border-destructive/40 px-3 py-2 text-sm text-destructive">
                    {bulkError}
                </p>
            )}

            {gruppen.length === 0 ? (
                <p className="rounded-lg border border-dashed px-3 py-10 text-center text-sm text-muted-foreground">
                    {suche.trim()
                        ? `Keine ${ansicht === 'kommend' ? 'kommenden' : 'vergangenen'} Spiele zu „${suche.trim()}“.`
                        : ansicht === 'kommend'
                            ? 'Zurzeit steht keine kommende Ansetzung in deinem DFBnet-Konto.'
                            : 'Noch keine vergangenen Spiele.'}
                </p>
            ) : gruppen.map((gruppe) => (
                <section key={gruppe.schluessel} aria-label={gruppe.titel} className="space-y-3">
                    <h2 className="flex items-baseline gap-2 pt-2 text-sm font-semibold">
                        {gruppe.titel}
                        <span className="text-xs font-normal text-muted-foreground">
                            {gruppe.spiele.length} {gruppe.spiele.length === 1 ? 'Spiel' : 'Spiele'}
                        </span>
                    </h2>
                    {gruppe.spiele.map((match) => (
                        <MatchCard
                            key={match._id}
                            match={match}
                            index={position.get(match._id) ?? 0}
                            onDownload={(fileFormat) => handleDownload(match, fileFormat)}
                            laufendeFormate={
                                (['docx', 'pdf'] as const).filter(
                                    f => laufendeDownloads.includes(`${match._id}:${f}`))
                            }
                            selected={selectedIds.includes(match._id)}
                            onToggleSelected={() => toggleSelected(match._id)}
                            onSaved={onReload}
                        />
                    ))}
                </section>
            ))}
        </div>
    );
}