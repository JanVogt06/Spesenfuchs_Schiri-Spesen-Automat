import {AppShell} from '@/components/layout/AppShell';
import {DFBCredentialsForm} from '@/components/auth/DFBCredentialsForm';
import {ChangePasswordForm} from '@/components/auth/ChangePasswordForm';
import {ThemeCard} from '@/components/settings/ThemeCard';
import {InstallCard} from '@/components/pwa/InstallHinweis';

export function SettingsPage() {
    return (
        <AppShell>
            {/* Settings Cards Grid */}
            <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2 xl:grid-cols-3">
                {/* DFB Credentials */}
                <DFBCredentialsForm/>

                {/* Passwort ändern */}
                <ChangePasswordForm/>

                {/* Theme / Dark Mode */}
                <ThemeCard/>

                {/* Installation als App */}
                <InstallCard/>
            </div>
        </AppShell>
    );
}
