import {Button} from '@/components/ui/button';
import {Zap, Loader2} from 'lucide-react';

interface GenerateButtonProps {
    isGenerating: boolean;
    onClick: () => void;
}

/** Navbar-Aktion zum Starten einer neuen Spesen-Generierung */
export function GenerateButton({isGenerating, onClick}: GenerateButtonProps) {
    return (
        <Button onClick={onClick} disabled={isGenerating} size="sm">
            {isGenerating ? (
                <>
                    <Loader2 className="size-4 animate-spin"/>
                    <span className="hidden sm:inline">Starte...</span>
                </>
            ) : (
                <>
                    <Zap className="size-4"/>
                    <span className="hidden sm:inline">Neue Spesen generieren</span>
                    <span className="sm:hidden">Generieren</span>
                </>
            )}
        </Button>
    );
}
