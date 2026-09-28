import {useState, useEffect, useLayoutEffect, type ReactNode} from 'react';
import {useNavigate, useLocation, Link} from 'react-router-dom';
import {Button} from '@/components/ui/button';
import {logout} from '@/lib/auth';
import {
    Receipt, Settings, LogOut, LayoutDashboard, IdCard, Trophy, FileText, Table2, Bug, Ellipsis,
} from 'lucide-react';
import {cn} from '@/lib/utils';

interface AppShellProps {
    children: ReactNode;
    /** Optionale Aktions-Elemente rechts in der Navbar (z.B. Generieren-Button) */
    actions?: ReactNode;
}

interface NavItem {
    label: string;
    path: string;
    icon: typeof LayoutDashboard;
}

// Die vier Reiter, die am Handy direkt in der Tab-Leiste stehen
const hauptItems: NavItem[] = [
    {label: 'Dashboard', path: '/dashboard', icon: LayoutDashboard},
    {label: 'Spesen', path: '/spesen', icon: FileText},
    {label: 'Saison', path: '/saison', icon: Trophy},
    {label: 'Ligen', path: '/ligen', icon: Table2},
];

// ... und die, die dort hinter "Mehr" liegen
const mehrItems: NavItem[] = [
    {label: 'Stammdaten', path: '/stammdaten', icon: IdCard},
    {label: 'Fehler melden', path: '/fehler-melden', icon: Bug},
    {label: 'Einstellungen', path: '/settings', icon: Settings},
];

const navItems = [...hauptItems, ...mehrItems];

/**
 * viewport-fit=cover, solange die Anwendung offen ist: erst damit meldet das
 * iPhone seine sicheren Raender, und die Tab-Leiste rueckt ueber den
 * Home-Balken. Kopfzeile und Inhalt halten sie ueber .app-rahmen frei.
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

export function AppShell({children, actions}: AppShellProps) {
    const navigate = useNavigate();
    const location = useLocation();
    const [mehrOffen, setMehrOffen] = useState(false);
    useSichereRaender();

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

    // Die Markierung der Tab-Leiste: ein Hauptreiter, sonst "Mehr"
    const hauptIndex = hauptItems.findIndex((item) => item.path === location.pathname);
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

                <nav className="ml-4 hidden items-center gap-1 lg:flex">
                    {navItems.map((item) => {
                        const isActive = location.pathname === item.path;
                        return (
                            <Button
                                key={item.path}
                                variant="ghost"
                                size="sm"
                                onClick={() => navigate(item.path)}
                                aria-label={item.label}
                                title={item.label}
                                className={cn(
                                    'text-muted-foreground',
                                    isActive && 'bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary'
                                )}
                            >
                                <item.icon className="size-4"/>
                                <span className="hidden xl:inline">{item.label}</span>
                            </Button>
                        );
                    })}
                </nav>

                <div className="ml-auto flex items-center gap-2">
                    {actions}
                    <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={logout}
                        className="hidden text-muted-foreground lg:inline-flex"
                        aria-label="Abmelden"
                        title="Abmelden"
                    >
                        <LogOut className="size-4"/>
                    </Button>
                </div>
            </header>

            <main className="app-rahmen app-unten mx-auto w-full max-w-[96rem] flex-1 pt-6 sm:pt-8">
                {children}
            </main>

            {/* Am Handy: "Mehr" klappt ueber der Tab-Leiste auf */}
            {mehrOffen && (
                <div className="fixed inset-0 z-40 lg:hidden">
                    <button
                        type="button"
                        className="absolute inset-0 bg-black/30 animate-in fade-in duration-200"
                        onClick={() => setMehrOffen(false)}
                        aria-label="Menü schließen"
                        tabIndex={-1}
                    />
                    <nav
                        id="mehr-menue"
                        aria-label="Weitere Seiten"
                        className="app-rahmen absolute inset-x-0 bottom-[calc(4.75rem+max(0.5rem,env(safe-area-inset-bottom)))] animate-in fade-in slide-in-from-bottom-4 duration-200"
                    >
                        <div className="mx-auto max-w-md rounded-2xl border bg-card p-2 shadow-xl">
                            {mehrItems.map((item) => {
                                const isActive = location.pathname === item.path;
                                return (
                                    <Button
                                        key={item.path}
                                        variant="ghost"
                                        onClick={() => gehZu(item.path)}
                                        aria-current={isActive ? 'page' : undefined}
                                        className={cn(
                                            'h-11 w-full justify-start text-muted-foreground',
                                            isActive && 'bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary'
                                        )}
                                    >
                                        <item.icon className="size-4"/>
                                        {item.label}
                                    </Button>
                                );
                            })}
                            <div className="my-1 border-t"/>
                            <Button
                                variant="ghost"
                                onClick={logout}
                                className="h-11 w-full justify-start text-muted-foreground"
                            >
                                <LogOut className="size-4"/>
                                Abmelden
                            </Button>
                        </div>
                    </nav>
                </div>
            )}

            {/* Tab-Leiste am Handy, schwebend ueber dem Inhalt wie unter iOS */}
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
                                    'relative flex h-14 flex-1 flex-col items-center justify-center gap-0.5 rounded-full text-[0.6875rem] font-medium transition-colors',
                                    isActive ? 'text-primary' : 'text-muted-foreground'
                                )}
                            >
                                <item.icon className="size-5"/>
                                {item.label}
                            </button>
                        );
                    })}
                    <button
                        type="button"
                        onClick={() => setMehrOffen((offen) => !offen)}
                        aria-expanded={mehrOffen}
                        aria-controls="mehr-menue"
                        className={cn(
                            'relative flex h-14 flex-1 flex-col items-center justify-center gap-0.5 rounded-full text-[0.6875rem] font-medium transition-colors',
                            mehrOffen || aufMehrSeite ? 'text-primary' : 'text-muted-foreground'
                        )}
                    >
                        <Ellipsis className="size-5"/>
                        Mehr
                    </button>
                </div>
            </nav>
        </div>
    );
}
