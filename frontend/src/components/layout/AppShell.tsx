import {useState, useEffect, type ReactNode} from 'react';
import {useNavigate, useLocation, Link} from 'react-router-dom';
import {Button} from '@/components/ui/button';
import {logout} from '@/lib/auth';
import {Receipt, Settings, LogOut, LayoutDashboard, IdCard, Trophy, FileText, Table2, Bug, Menu, X} from 'lucide-react';
import {cn} from '@/lib/utils';

interface AppShellProps {
    children: ReactNode;
    /** Optionale Aktions-Elemente rechts in der Navbar (z.B. Generieren-Button) */
    actions?: ReactNode;
}

const navItems = [
    {label: 'Dashboard', path: '/dashboard', icon: LayoutDashboard},
    {label: 'Spesen', path: '/spesen', icon: FileText},
    {label: 'Saison', path: '/saison', icon: Trophy},
    {label: 'Ligen', path: '/ligen', icon: Table2},
    {label: 'Stammdaten', path: '/stammdaten', icon: IdCard},
    {label: 'Fehler melden', path: '/fehler-melden', icon: Bug},
    {label: 'Einstellungen', path: '/settings', icon: Settings},
];

export function AppShell({children, actions}: AppShellProps) {
    const navigate = useNavigate();
    const location = useLocation();
    // Sieben Reiter passen erst ab lg nebeneinander; darunter klappt ein Menue auf
    const [menuOffen, setMenuOffen] = useState(false);

    useEffect(() => {
        if (!menuOffen) return;
        const schliessen = (e: KeyboardEvent) => {
            if (e.key === 'Escape') setMenuOffen(false);
        };
        window.addEventListener('keydown', schliessen);
        return () => window.removeEventListener('keydown', schliessen);
    }, [menuOffen]);

    return (
        <div className="flex min-h-screen flex-col bg-background text-foreground">
            <header className="sticky top-0 z-40 border-b bg-card">
                <div className="flex h-14 items-center gap-3 px-4 sm:px-6">
                    <Link to="/dashboard" className="flex shrink-0 items-center gap-2.5">
                        <span className="grid size-7 place-items-center rounded-lg bg-primary text-primary-foreground">
                            <Receipt className="size-4"/>
                        </span>
                        <span className="hidden text-sm font-semibold tracking-tight whitespace-nowrap sm:block sm:text-base">
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
                        <Button
                            variant="ghost"
                            size="icon-sm"
                            onClick={() => setMenuOffen((offen) => !offen)}
                            className="text-muted-foreground lg:hidden"
                            aria-label={menuOffen ? 'Menü schließen' : 'Menü öffnen'}
                            aria-expanded={menuOffen}
                            aria-controls="app-menu"
                        >
                            {menuOffen ? <X className="size-5"/> : <Menu className="size-5"/>}
                        </Button>
                    </div>
                </div>

                {menuOffen && (
                    <nav id="app-menu" className="border-t px-2 py-2 sm:px-4 lg:hidden">
                        {navItems.map((item) => {
                            const isActive = location.pathname === item.path;
                            return (
                                <Button
                                    key={item.path}
                                    variant="ghost"
                                    onClick={() => {
                                        setMenuOffen(false);
                                        navigate(item.path);
                                    }}
                                    aria-current={isActive ? 'page' : undefined}
                                    className={cn(
                                        'w-full justify-start text-muted-foreground',
                                        isActive && 'bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary'
                                    )}
                                >
                                    <item.icon className="size-4"/>
                                    {item.label}
                                </Button>
                            );
                        })}
                        <div className="my-2 border-t"/>
                        <Button
                            variant="ghost"
                            onClick={logout}
                            className="w-full justify-start text-muted-foreground"
                        >
                            <LogOut className="size-4"/>
                            Abmelden
                        </Button>
                    </nav>
                )}
            </header>

            <main className="mx-auto w-full max-w-[96rem] flex-1 px-4 py-6 sm:px-6 sm:py-8">
                {children}
            </main>
        </div>
    );
}
