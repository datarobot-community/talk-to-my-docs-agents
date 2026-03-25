import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { ROUTES } from './routes';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';

const navItems = [
    { label: 'Connected sources', to: ROUTES.SETTINGS_SOURCES },
    { label: 'Chats', to: ROUTES.SETTINGS_CHATS },
];

export const SettingsLayout = () => {
    const location = useLocation();
    return (
        <div className="align-start flex h-full flex-1 flex-col justify-start gap-4 p-4">
            {/* Side navigation within settings */}

            <nav className="w-full">
                <Tabs
                    value={
                        navItems.find(item => item.to === location.pathname)?.to || navItems[0].to
                    }
                >
                    <TabsList variant="underline">
                        {navItems.map(item => (
                            <TabsTrigger key={item.to} value={item.to} asChild>
                                <NavLink to={item.to}>{item.label}</NavLink>
                            </TabsTrigger>
                        ))}
                    </TabsList>
                </Tabs>
            </nav>
            {/* Active tab content */}
            <main className="w-full max-w-3xl overflow-y-auto">
                <Outlet />
            </main>
        </div>
    );
};
