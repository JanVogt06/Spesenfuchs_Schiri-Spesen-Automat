import {useEffect} from 'react';
import {BrowserRouter, Routes, Route, Navigate, useLocation} from 'react-router-dom';
import {LoginPage} from './pages/Login';
import {RegisterPage} from './pages/Register';
import {LandingPage} from './pages/Landing';
import {DashboardPage} from './pages/Dashboard';
import {SettingsPage} from './pages/Settings';
import {SpielePage} from './pages/Spiele';
import {SaisonPage} from './pages/Saison';
import {SpielberichtPage} from './pages/Spielbericht';
import {BeobachtungenPage} from './pages/Beobachtungen';
import {StammdatenPage} from './pages/Stammdaten';
import {LigenPage} from './pages/Ligen';
import {BugReportPage} from './pages/BugReport';
import {isAuthenticated} from './lib/auth';
import {Datenschutz} from './pages/Datenschutz';

function ProtectedRoute({children}: { children: React.ReactNode }) {
    if (!isAuthenticated()) {
        return <Navigate to="/login" replace/>;
    }
    return <>{children}</>;
}

/**
 * Scrolls to the top on page change. The BrowserRouter otherwise keeps the
 * scroll position, and a link from far down on the landing page opened
 * the privacy policy at its end.
 */
function NachObenBeiSeitenwechsel() {
    const {pathname} = useLocation();

    useEffect(() => {
        window.scrollTo(0, 0);
    }, [pathname]);

    return null;
}

function App() {
    return (
        <BrowserRouter>
            <NachObenBeiSeitenwechsel/>
            <Routes>
                {/* Public Routes */}
                <Route path="/" element={<LandingPage/>}/>
                <Route path="/login" element={<LoginPage/>}/>
                <Route path="/register" element={<RegisterPage/>}/>
                <Route path="/datenschutz" element={<Datenschutz />} />

                {/* Protected Routes */}
                <Route
                    path="/dashboard"
                    element={
                        <ProtectedRoute>
                            <DashboardPage/>
                        </ProtectedRoute>
                    }
                />

                <Route
                    path="/spiele"
                    element={
                        <ProtectedRoute>
                            <SpielePage/>
                        </ProtectedRoute>
                    }
                />

                {/* The tab used to be called "Spesen" - old bookmarks lead on */}
                <Route path="/spesen" element={<Navigate to="/spiele" replace/>}/>

                <Route
                    path="/saison"
                    element={
                        <ProtectedRoute>
                            <SaisonPage/>
                        </ProtectedRoute>
                    }
                />

                <Route
                    path="/spielbericht/:id"
                    element={
                        <ProtectedRoute>
                            <SpielberichtPage/>
                        </ProtectedRoute>
                    }
                />

                <Route
                    path="/beobachtungen"
                    element={
                        <ProtectedRoute>
                            <BeobachtungenPage/>
                        </ProtectedRoute>
                    }
                />

                <Route
                    path="/ligen"
                    element={
                        <ProtectedRoute>
                            <LigenPage/>
                        </ProtectedRoute>
                    }
                />

                <Route
                    path="/fehler-melden"
                    element={
                        <ProtectedRoute>
                            <BugReportPage/>
                        </ProtectedRoute>
                    }
                />

                <Route
                    path="/stammdaten"
                    element={
                        <ProtectedRoute>
                            <StammdatenPage/>
                        </ProtectedRoute>
                    }
                />

                <Route
                    path="/settings"
                    element={
                        <ProtectedRoute>
                            <SettingsPage/>
                        </ProtectedRoute>
                    }
                />
            </Routes>
        </BrowserRouter>
    );
}

export default App;