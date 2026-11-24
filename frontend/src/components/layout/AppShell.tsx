import {useState, useEffect, useLayoutEffect, type ReactNode} from 'react';
import {useNavigate, useLocation, Link} from 'react-router-dom';
import {Button} from '@/components/ui/button';
import {logout} from '@/lib/auth';
import {
    Receipt, Settings, LogOut, LayoutDashboard, IdCard, Trophy, CalendarDays, ChartColumn, Table2, Bug, Ellipsis, ClipboardCheck,
} from 'lucide-react';
import {cn} from '@/lib/utils';
import {useDfbLoginStatus} from '@/hooks/useDfbLoginStatus';
import {DfbLoginHinweis} from '@/components/layout/DfbLoginHinweis';

interface AppShellProps {
    children: ReactNode;
    /** Page heading; also appears in the browser tab */
    titel?: string;
    /** One line below the heading saying what the page is for */
    beschreibung?: ReactNode;
    /** Optional action elements on the right of the navbar (e.g. the refresh button) */
    actions?: ReactNode;
}

interface NavItem {
    label: string;
    /** Shorter label for the narrow tab bar on phones */
    kurz?: string;
    path: string;
    icon: typeof LayoutDashboard;
}

// The main tabs: in the header and, on phones, directly in the tab bar
const hauptItems: NavItem[] = [
    {label: 'Übersicht', path: '/dashboard', icon: LayoutDashboard},
    {label: 'Spiele', path: '/spiele', icon: CalendarDays},
    {label: 'Saison', path: '/saison', icon: Trophy},
    {label: 'Statistik', path: '/statistik', icon: ChartColumn},
    {label: 'Beobachtungen', kurz: 'Noten', path: '/beobachtungen', icon: ClipboardCheck},
];

// ... and those that sit behind "Mehr" at both widths
const mehrItems: NavItem[] = [
    {label: 'Ligen', path: '/ligen', icon: Table2},
    {label: 'Stammdaten', path: '/stammdaten', icon: IdCard},
    {label: 'Einstellungen', path: '/settings', icon: Settings},
    {label: 'Fehler melden', path: '/fehler-melden', icon: Bug},
];

/** Red dot on a tab that needs attention */
function Warnpunkt({className}: {className?: string}) {
    return (
        <span
            aria-hidden="true"
            className={cn('absolute size-2 rounded-full bg-destructive ring-2 ring-card', className)}
        />
    );
}

/**
 * viewport-fit=cover while the application is open: only then does the
 * iPhone report its safe-area insets, and the tab bar moves above the
 * home indicator. Header and content keep clear of them via .app-rahmen.
 */
function useSichereRaender() {
    useLayoutEffect(() => {
        const viewport = document.querySelector<HTMLMetaElement>('meta[name="viewport"]');
        const vorher = viewport?.content;
        if (viewport && !viewport.content.includes('viewport-fit')) {
            viewport.content = `${viewport.content}, viewport-fit=cover`;
        }
        return () => {
            if (viewport && vorher !== undefined) viewport.content = vorher;
        };
    }, []);
}

/** Page title in the browser tab and the app switcher while the page is open */
function useDokumentTitel(titel?: string) {
    useEffect(() => {
        if (!titel) return;
        const vorher = document.title;
        document.title = `${titel} · Spesenfuchs`;
        return () => {
            document.title = vorher;
        };
    }, [titel]);
}

export function AppShell({children, titel, beschreibung, actions}: AppShellProps) {
    const navigate = useNavigate();
    const location = useLocation();
    const [mehrOffen, setMehrOffen] = useState(false);
    const dfbAbgelehntSeit = useDfbLoginStatus();
    useSichereRaender();
    useDokumentTitel(titel);

    useEffect(() => {
        if (!mehrOffen) return;
        const schliessen = (e: KeyboardEvent) => {
            if (e.key === 'Escape') setMehrOffen(false);
        };
        window.addEventListener('keydown', schliessen);
        return () => window.removeEventListener('keydown', schliessen);
    }, [mehrOffen]);

    const gehZu = (path: string) => {
        setMehrOffen(false);
        navigate(path);
    };

    // Which tab lights up: a match report belongs to the list it was opened
    // from, everything else outside the main tabs belongs to "Mehr"
    const aktiverPfad = location.pathname.startsWith('/spielbericht/')
        ? (new URLSearchParams(location.search).get('von') === 'saison' ? '/saison' : '/spiele')
        : location.pathname;
    const hauptIndex = hauptItems.findIndex((item) => item.path === aktiverPfad);
    const aufMehrSeite = hauptIndex === -1;
    const markierung = mehrOffen || aufMehrSeite ? hauptItems.length : hauptIndex;
    const tabs = hauptItems.length + 1;

    return (
        <div className="flex min-h-screen flex-col bg-background text-foreground">
            <header className="app-rahmen sticky top-0 z-40 flex h-14 items-center gap-3 border-b bg-card">
                <Link to="/dashboard" className="flex shrink-0 items-center gap-2.5">
                    <span className="grid size-7 place-items-center rounded-lg bg-primary text-primary-foreground">
                        <Receipt className="size-4"/>
                    </span>
                    <span className="text-sm font-semibold tracking-tight whitespace-nowrap sm:text-base">
                        Spesenfuchs
                    </span>
                </Link>

                <nav aria-label="Hauptreiter" className="ml-4 hidden items-center gap-1 lg:flex">
                    {hauptItems.map((item, index) => {
                        const isActive = index === hauptIndex;
                        return (
                            <Button
                                key={item.path}
                                variant="ghost"
                                size="sm"
                                onClick={() => gehZu(item.path)}
                                aria-current={isActive ? 'page' : undefined}
                                className={cn(
                                    'text-muted-foreground',
                                    isActive && 'bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary'
                                )}
                            >
                                <item.icon className="size-4"/>
                                {item.label}
                            </Button>
                        );
                    })}
                </nav>

                <div className="ml-auto flex items-center gap-2">
                    {actions}
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setMehrOffen((offen) => !offen)}
                        aria-expanded={mehrOffen}
                        aria-controls="mehr-menue"
                        className={cn(
                            'hidden text-muted-foreground lg:inline-flex',
                            (mehrOffen || aufMehrSeite) && 'bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary'
                        )}
                    >
                        <span className="relative">
                            <Ellipsis className="size-4"/>
                            {dfbAbgelehntSeit && <Warnpunkt className="-top-1 -right-1"/>}
                        </span>
                        Mehr
                    </Button>
                </div>
            </header>

            <main className="app-rahmen app-unten mx-auto w-full max-w-[96rem] flex-1 pt-6 sm:pt-8">
                {dfbAbgelehntSeit && <DfbLoginHinweis abgelehntSeit={dfbAbgelehntSeit}/>}
                {titel && (
                    <div className="mb-6">
                        <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">{titel}</h1>
                        {beschreibung && (
                            <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{beschreibung}</p>
                        )}
                    </div>
                )}
                {children}
            </main>

            {/* "Mehr" opens above the tab bar on phones, on desktop
                below the button on the right of the header */}
            {mehrOffen && (
                <div className="fixed inset-0 z-40">
                    <button
                        type="button"
                        className="absolute inset-0 bg-black/30 animate-in fade-in duration-200 lg:bg-transparent"
                        onClick={() => setMehrOffen(false)}
                        aria-label="Menü schließen"
                        tabIndex={-1}
                    />
                    <nav
                        id="mehr-menue"
                        aria-label="Weitere Seiten"
                        className="app-rahmen absolute inset-x-0 bottom-[calc(4.75rem+max(0.5rem,env(safe-area-inset-bottom)))] animate-in fade-in slide-in-from-bottom-4 duration-200 lg:top-15 lg:bottom-auto lg:left-auto lg:slide-in-from-top-2"
                    >
                        <div className="mx-auto max-w-md rounded-2xl border bg-card p-2 shadow-xl lg:mx-0 lg:w-60 lg:rounded-xl lg:p-1.5">
                            {mehrItems.map((item) => {
                                const isActive = location.pathname === item.path;
                                return (
                                    <Button
                                        key={item.path}
                                        variant="ghost"
                                        onClick={() => gehZu(item.path)}
                                        aria-current={isActive ? 'page' : undefined}
                                        className={cn(
                                            'h-11 w-full justify-start text-muted-foreground lg:h-9',
                                            isActive && 'bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary'
                                        )}
                                    >
                                        <span className="relative">
                                            <item.icon className="size-4"/>
                                            {dfbAbgelehntSeit && item.path === '/settings' && (
                                                <Warnpunkt className="-top-1 -right-1"/>
                                            )}
                                        </span>
                                        {item.label}
                                    </Button>
                                );
                            })}
                            <div className="my-1 border-t"/>
                            <Button
                                variant="ghost"
                                onClick={logout}
                                className="h-11 w-full justify-start text-muted-foreground lg:h-9"
                            >
                                <LogOut className="size-4"/>
                                Abmelden
                            </Button>
                        </div>
                    </nav>
                </div>
            )}

            {/* Tab bar on phones, floating above the content like on iOS */}
            <nav
                aria-label="Hauptnavigation"
                className="app-rahmen pointer-events-none fixed inset-x-0 bottom-0 z-50 pb-[max(0.5rem,env(safe-area-inset-bottom))] lg:hidden"
            >
                <div className="pointer-events-auto relative mx-auto flex max-w-md rounded-full border bg-card/85 p-1 shadow-lg backdrop-blur-xl">
                    <span
                        aria-hidden="true"
                        className="absolute inset-y-1 left-1 rounded-full bg-primary/12 transition-transform duration-300 ease-out motion-reduce:transition-none"
                        style={{
                            width: `calc((100% - 0.5rem) / ${tabs})`,
                            transform: `translateX(${markierung * 100}%)`,
                        }}
                    />
                    {hauptItems.map((item, index) => {
                        const isActive = !mehrOffen && index === hauptIndex;
                        return (
                            <button
                                key={item.path}
                                type="button"
                                onClick={() => gehZu(item.path)}
                                aria-current={index === hauptIndex ? 'page' : undefined}
                                className={cn(
                                    'relative flex h-14 min-w-0 flex-1 flex-col items-center justify-center gap-0.5 rounded-full text-[0.6875rem] font-medium transition-colors',
                                    isActive ? 'text-primary' : 'text-muted-foreground'
                                )}
                            >
                                <item.icon className="size-5"/>
                                {item.kurz ?? item.label}
                            </button>
                        );
                    })}
                    <button
                        type="button"
                        onClick={() => setMehrOffen((offen) => !offen)}
                        aria-expanded={mehrOffen}
                        aria-controls="mehr-menue"
                        className={cn(
                            'relative flex h-14 min-w-0 flex-1 flex-col items-center justify-center gap-0.5 rounded-full text-[0.6875rem] font-medium transition-colors',
                            mehrOffen || aufMehrSeite ? 'text-primary' : 'text-muted-foreground'
                        )}
                    >
                        <span className="relative">
                            <Ellipsis className="size-5"/>
                            {dfbAbgelehntSeit && <Warnpunkt className="-top-0.5 -right-1"/>}
                        </span>
                        Mehr
                    </button>
                </div>
            </nav>
        </div>
    );
}
