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
import { useEffect } from 'react';
import { AppSidebar } from '@/components/layout/app-sidebar.tsx';
import { AppHeader } from '@/components/layout/app-header';
import Pages from '@/pages';
import { SidebarProvider } from '@/components/ui/sidebar';
import { Spinner } from '@/components/ui/spinner';
import { useAppState } from '@/state';

import './App.css';
import { useLlmCatalog } from '@/api/chat/hooks';

function App() {
    const { data: availableLlmCatalog, isLoading, isFetched } = useLlmCatalog();
    const { selectedLlmModel, setSelectedLlmModel, setAvailableLlmModels, availableLlmModels } =
        useAppState();
    useEffect(() => {
        if (isFetched && availableLlmCatalog?.length && !availableLlmModels) {
            setAvailableLlmModels(availableLlmCatalog);
            if (!selectedLlmModel) {
                setSelectedLlmModel(availableLlmCatalog[0]);
            }
        }
    }, [
        setAvailableLlmModels,
        setSelectedLlmModel,
        selectedLlmModel,
        availableLlmCatalog,
        isFetched,
        availableLlmModels,
    ]);

    return (
        <SidebarProvider>
            <div className="flex flex-1 min-h-screen dark">
                <AppSidebar />
                <div className="flex flex-col flex-1 h-screen">
                    {isLoading ? (
                        <div
                            className="flex items-center gap-3 h-screen justify-center"
                            data-testid="app-loader"
                        >
                            <Spinner>Loading...</Spinner>
                        </div>
                    ) : (
                        <>
                            <AppHeader />
                            <Pages />
                        </>
                    )}
                </div>
            </div>
        </SidebarProvider>
    );
}

export default App;
