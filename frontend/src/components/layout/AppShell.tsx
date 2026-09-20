import type {ReactNode} from 'react';
import {useNavigate, useLocation, Link} from 'react-router-dom';
import {Button} from '@/components/ui/button';
import {logout} from '@/lib/auth';
import {Receipt, Settings, LogOut, LayoutDashboard, IdCard, Trophy, FileText} from 'lucide-react';
import {cn} from '@/lib/utils';

interface AppShellProps {
    children: ReactNode;
    /** Optionale Aktions-Elemente rechts in der Navbar (z.B. Generieren-Button) */
    actions?: ReactNode;
}

export function AppShell({children, actions}: AppShellProps) {
    const navigate = useNavigate();
    const location = useLocation();

    const navItems = [
        {label: 'Dashboard', path: '/dashboard', icon: LayoutDashboard},
        {label: 'Spesen', path: '/spesen', icon: FileText},
        {label: 'Saison', path: '/saison', icon: Trophy},
        {label: 'Stammdaten', path: '/stammdaten', icon: IdCard},
        {label: 'Einstellungen', path: '/settings', icon: Settings},
    ];

    return (
        <div className="flex min-h-screen flex-col bg-background text-foreground">
            <header className="sticky top-0 z-40 flex h-14 items-center gap-3 border-b bg-card px-4 sm:px-6">
                <Link to="/dashboard" className="flex items-center gap-2.5">
                    <span className="grid size-7 place-items-center rounded-lg bg-primary text-primary-foreground">
                        <Receipt className="size-4"/>
                    </span>
                    <span className="hidden text-sm font-semibold tracking-tight whitespace-nowrap sm:block sm:text-base">
                        Spesenfuchs
                    </span>
                </Link>

                <nav className="ml-2 flex items-center gap-1 sm:ml-4">
                    {navItems.map((item) => {
                        const isActive = location.pathname === item.path;
                        return (
                            <Button
                                key={item.path}
                                variant="ghost"
                                size="sm"
                                onClick={() => navigate(item.path)}
                                className={cn(
                                    'text-muted-foreground',
                                    isActive && 'bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary'
                                )}
                            >
                                <item.icon className="size-4"/>
                                <span className="hidden sm:inline">{item.label}</span>
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
                        className="text-muted-foreground"
                        aria-label="Abmelden"
                    >
                        <LogOut className="size-4"/>
                    </Button>
                </div>
            </header>

            <main className="mx-auto w-full max-w-[96rem] flex-1 px-4 py-6 sm:px-6 sm:py-8">
                {children}
            </main>
        </div>
    );
}
