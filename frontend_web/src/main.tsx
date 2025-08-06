/*
 * Copyright 2025 DataRobot, Inc.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter as Router } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppStateProvider } from '@/state';
import { authKeys } from '@/api/auth/hooks';
import { chatKeys } from '@/api/chat/keys';
import { getCurrentUser } from '@/api/auth/requests';
import { getBaseUrl } from '@/lib/utils.ts';

import App from './App.tsx';
import { getLlmCatalog } from '@/api/chat/requests.ts';

const queryClient = new QueryClient();

// Prefetch current user
queryClient.prefetchQuery({
    queryKey: authKeys.currentUser,
    queryFn: () => getCurrentUser(),
    retry: false,
});
// Prefetch available LLMs
queryClient.prefetchQuery({
    queryKey: chatKeys.llmCatalog,
    queryFn: () => getLlmCatalog(),
    retry: 5,
    retryDelay: 2000,
});
const basename = getBaseUrl();

createRoot(document.getElementById('root')!).render(
    <StrictMode>
        <QueryClientProvider client={queryClient}>
            <Router basename={basename}>
                <AppStateProvider>
                    <App />
                </AppStateProvider>
            </Router>
        </QueryClientProvider>
    </StrictMode>
);
