import {useState} from 'react';
import type {MatchData} from '@/lib/matches';
import {downloadMatchDocument, downloadMatchesAsZip} from '@/lib/matches';
import {MatchCard} from '../matches/MatchCard';
import {Button} from '@/components/ui/button';
import {Calendar, Download} from 'lucide-react';

interface MatchListProps {
    matches: MatchData[];
}

export function MatchList({matches}: MatchListProps) {
    const [downloadingFile, setDownloadingFile] = useState<string | null>(null);
    const [selectedIds, setSelectedIds] = useState<number[]>([]);
    const [isBulkDownloading, setIsBulkDownloading] = useState(false);
    const [bulkError, setBulkError] = useState('');

    const handleDownload = async (match: MatchData, fileFormat: 'docx' | 'pdf') => {
        const docxName = match._filename || `spiel_${match._id}.docx`;
        const filename = fileFormat === 'pdf' ? docxName.replace(/\.docx$/i, '.pdf') : docxName;

        setDownloadingFile(filename);
        try {
            await downloadMatchDocument(match._id, fileFormat, filename);
        } catch (error) {
            console.error('Download failed:', error);
            alert('Download fehlgeschlagen');
        } finally {
            setDownloadingFile(null);
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
            setBulkError('Sammel-Download fehlgeschlagen. Bitte erneut versuchen.');
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
                    Starte die erste Generierung mit dem Button oben.
                </p>
            </div>
        );
    }

    return (
        <div className="space-y-3">
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

            {matches.map((match, index) => {
                const filename = match._filename || `spiel_${index + 1}.docx`;

                return (
                    <MatchCard
                        key={match._id}
                        match={match}
                        index={index}
                        filename={filename}
                        onDownload={(fileFormat) => handleDownload(match, fileFormat)}
                        downloadingFilename={downloadingFile}
                        selected={selectedIds.includes(match._id)}
                        onToggleSelected={() => toggleSelected(match._id)}
                    />
                );
            })}
        </div>
    );
}