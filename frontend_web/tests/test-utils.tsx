import { ReactNode } from 'react';
import { render } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, InitialEntry } from 'react-router-dom';
import { AppStateProvider, AppState } from '@/state';

const createTestQueryClient = () =>
    new QueryClient({
        defaultOptions: {
            queries: {
                retry: false,
            },
        },
    });

export function renderWithProviders(
    children: ReactNode,
    initialState?: AppState,
    initialRoute?: InitialEntry
) {
    const queryClient = createTestQueryClient();
    const initialEntries = initialRoute ? [initialRoute] : undefined;

    return render(
        <MemoryRouter initialEntries={initialEntries}>
            <QueryClientProvider client={queryClient}>
                <AppStateProvider initialState={initialState}>{children}</AppStateProvider>
            </QueryClientProvider>
        </MemoryRouter>
    );
}
