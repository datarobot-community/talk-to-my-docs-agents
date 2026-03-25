'use client';

import { useCurrentUser } from '@/api/auth/hooks';
import { useState, createContext, useContext, useLayoutEffect, useEffect, useMemo } from 'react';

export type Theme = 'light' | 'dark';

interface ThemeContextType {
    theme: 'light' | 'dark';
    userTheme: Theme | 'system';
}

const PREFERS_COLOR_SCHEME_DARK = '(prefers-color-scheme: dark)';

const ThemeContext = createContext<ThemeContextType>({
    theme: 'dark',
    userTheme: 'system',
});

export const useTheme = () => {
    return useContext(ThemeContext);
};

/**
 * This hook is used to determine which system theme user has configured
 * and set up listeners for system theme changes
 * */
function useSystemTheme() {
    const [systemTheme, setSystemTheme] = useState(() => {
        const isSystemDarkTheme = window.matchMedia(PREFERS_COLOR_SCHEME_DARK).matches;
        if (isSystemDarkTheme) {
            return 'dark';
        }
        return 'light';
    });

    useEffect(() => {
        const darkModeQuery = window.matchMedia(PREFERS_COLOR_SCHEME_DARK);

        function handleThemeChange(event: MediaQueryListEvent) {
            setSystemTheme(event.matches ? 'dark' : 'light');
        }

        darkModeQuery.addEventListener('change', handleThemeChange);

        return () => {
            darkModeQuery.removeEventListener('change', handleThemeChange);
        };
    }, []);

    return {
        systemTheme: systemTheme as 'light' | 'dark',
    };
}

const themeKey = 'app-theme';

const getSystemTheme = () => {
    return window.matchMedia(PREFERS_COLOR_SCHEME_DARK).matches ? 'dark' : 'light';
};

const getInitialTheme = () => {
    if (typeof window !== 'undefined') {
        const savedTheme = localStorage.getItem(themeKey);
        if (savedTheme && savedTheme !== 'system') {
            return savedTheme as Theme;
        }
        return getSystemTheme();
    }
    return 'light';
};

export const ThemeProvider = ({
    children,
}: {
    children: React.ReactNode | ((props: { theme: Theme }) => React.ReactNode);
}) => {
    const { data: user } = useCurrentUser();
    const { systemTheme } = useSystemTheme();
    const theme = useMemo(() => {
        if (user?.theme === 'system') {
            return systemTheme;
        } else if (user?.theme) {
            return user.theme;
        }
        return getInitialTheme();
    }, [user?.theme, systemTheme]);

    const userTheme = user?.theme || systemTheme;

    useLayoutEffect(() => {
        document.documentElement.classList.toggle('dark', theme === 'dark');
    }, [theme]);

    useEffect(() => {
        if (user?.theme) {
            localStorage.setItem(themeKey, user.theme);
        }
    }, [user?.theme]);

    const value = useMemo(() => ({ theme, userTheme }), [theme, userTheme]);

    return (
        <ThemeContext.Provider value={value}>
            {typeof children === 'function' ? children({ theme }) : children}
        </ThemeContext.Provider>
    );
};
