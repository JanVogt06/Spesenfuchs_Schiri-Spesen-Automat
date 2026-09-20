import {BrowserRouter, Routes, Route, Navigate} from 'react-router-dom';
import {LoginPage} from './pages/Login';
import {RegisterPage} from './pages/Register';
import {LandingPage} from './pages/Landing';
import {DashboardPage} from './pages/Dashboard';
import {SettingsPage} from './pages/Settings';
import {StammdatenPage} from './pages/Stammdaten';
import {isAuthenticated} from './lib/auth';
import {Datenschutz} from './pages/Datenschutz';

function ProtectedRoute({children}: { children: React.ReactNode }) {
    if (!isAuthenticated()) {
        return <Navigate to="/login" replace/>;
    }
    return <>{children}</>;
}

function App() {
    return (
        <BrowserRouter>
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