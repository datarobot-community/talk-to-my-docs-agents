import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { SidebarTrigger } from '@/components/ui/sidebar';
import { ScrollArea } from '@/components/ui/scroll-area';
import { ChevronDown, Plus } from 'lucide-react';
import { useAppState } from '@/state';
import { useLocation, useNavigate } from 'react-router-dom';
import { PATHS } from '@/constants/paths';
import { ROUTES } from '@/pages/routes';
import {
    DropdownMenu,
    DropdownMenuTrigger,
    DropdownMenuContent,
    DropdownMenuItem,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { Search } from 'lucide-react';

export function AppHeader() {
    const { selectedLlmModel, setSelectedLlmModel, availableLlmModels } = useAppState();
    const location = useLocation();
    const navigate = useNavigate();
    const [search, setSearch] = useState('');
    const filteredItems = availableLlmModels?.filter(
        item =>
            item.name.toLowerCase().includes(search.toLowerCase()) ||
            item.model.toLowerCase().includes(search.toLowerCase())
    );

    const shouldShowLLMSelector = location.pathname.startsWith(PATHS.CHAT);
    const shouldShowCreateButton = location.pathname === PATHS.KNOWLEDGE_BASES;

    return (
        <header className="h-16 px-4 flex items-center justify-between" data-testid="app-header">
            <div className="flex gap-1">
                <SidebarTrigger className="h-9" />
                {shouldShowLLMSelector && (
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild data-testid="dropdown-model-selector-trigger">
                            <Button
                                variant="ghost"
                                className="h-9 cursor-pointer hover:no-underline"
                            >
                                <span>{selectedLlmModel.name}</span>
                                <ChevronDown className="h-4 w-4" />
                            </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent
                            align="start"
                            data-testid="dropdown-model-selector-menu-content"
                        >
                            <div className="relative">
                                <Search className="absolute left-2.5 top-1/2 h-4 w-4 text-muted-foreground -translate-y-1/2" />
                                <Input
                                    placeholder="Search..."
                                    value={search}
                                    onChange={e => setSearch(e.target.value)}
                                    onKeyDown={e => e.stopPropagation()}
                                    className="pl-8 h-8"
                                    data-testid="dropdown-model-selector-search"
                                />
                            </div>

                            <ScrollArea className="w-full max-h-80 overflow-y-scroll  scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-slate-300">
                                {filteredItems?.map((llmModel, index) => (
                                    <DropdownMenuItem
                                        className="hover:bg-muted cursor-pointer"
                                        onSelect={() => setSelectedLlmModel(llmModel)}
                                        data-testid={`dropdown-model-selector-item-${llmModel.llmId.toLowerCase()}`}
                                        key={`llm-${llmModel.llmId}-${index}`}
                                    >
                                        {llmModel.name}
                                    </DropdownMenuItem>
                                ))}
                            </ScrollArea>
                        </DropdownMenuContent>
                    </DropdownMenu>
                )}
            </div>
            {shouldShowCreateButton && (
                <Button
                    variant="ghost"
                    onClick={() => navigate(ROUTES.ADD_KNOWLEDGE_BASE)}
                    className="flex items-center gap-2"
                >
                    <Plus className="h-4 w-4" />
                    Create knowledge base
                </Button>
            )}
        </header>
    );
}
