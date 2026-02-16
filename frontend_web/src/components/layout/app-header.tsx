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
import { Search, ChevronLeft } from 'lucide-react';
import { useIsMobile } from '@/hooks';
import { useTranslation } from '@/lib/i18n';

export function AppHeader() {
    const { t } = useTranslation();
    const { selectedLlmModel, setSelectedLlmModel, availableLlmModels } = useAppState();
    const location = useLocation();
    const navigate = useNavigate();
    const [search, setSearch] = useState('');
    const filteredItems = availableLlmModels?.filter(
        item =>
            item.name.toLowerCase().includes(search.toLowerCase()) ||
            item.model.toLowerCase().includes(search.toLowerCase())
    );

    const isMobile = useIsMobile();
    const shouldShowLLMSelector = location.pathname.startsWith(PATHS.CHAT);
    const shouldShowCreateButton = location.pathname === PATHS.KNOWLEDGE_BASES;
    const shouldShowGoToKbButton =
        location.pathname.startsWith(PATHS.KNOWLEDGE_BASES) &&
        location.pathname !== PATHS.KNOWLEDGE_BASES;
    const shouldShowHeader = !location.pathname.startsWith(PATHS.SETTINGS.ROOT);
    if (!shouldShowHeader) {
        return null;
    }
    return (
        <header className="flex h-16 items-center justify-between px-4" data-testid="app-header">
            <div className="flex gap-1">
                {isMobile && <SidebarTrigger className="h-9" />}
                {shouldShowLLMSelector && (
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild data-testid="dropdown-model-selector-trigger">
                            <Button
                                variant="ghost"
                                className="h-9 cursor-pointer hover:no-underline"
                            >
                                <span>{selectedLlmModel.name}</span>
                                <ChevronDown className="size-4" />
                            </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent
                            align="start"
                            data-testid="dropdown-model-selector-menu-content"
                            className="p-2"
                        >
                            <div className="relative">
                                <Search className="pointer-events-none absolute top-1/2 left-2 size-4 -translate-y-1/2 text-muted-foreground select-none" />
                                <Input
                                    placeholder={t('Search...')}
                                    value={search}
                                    onChange={e => setSearch(e.target.value)}
                                    onKeyDown={e => e.stopPropagation()}
                                    className="pl-8"
                                    data-testid="dropdown-model-selector-search"
                                />
                            </div>

                            <ScrollArea className="w-full">
                                <div className="max-h-80">
                                    {filteredItems?.map((llmModel, index) => (
                                        <DropdownMenuItem
                                            onSelect={() => setSelectedLlmModel(llmModel)}
                                            data-testid={`dropdown-model-selector-item-${llmModel.llmId.toLowerCase()}`}
                                            key={`llm-${llmModel.llmId}-${index}`}
                                        >
                                            {llmModel.name}
                                        </DropdownMenuItem>
                                    ))}
                                </div>
                            </ScrollArea>
                        </DropdownMenuContent>
                    </DropdownMenu>
                )}
                {shouldShowGoToKbButton && (
                    <Button
                        variant="ghost"
                        data-testid="go-to-kb-button"
                        onClick={() => navigate(ROUTES.KNOWLEDGE_BASES)}
                        className="flex items-center gap-2"
                    >
                        <ChevronLeft className="size-4" />
                        {t('Knowledge bases')}
                    </Button>
                )}
            </div>
            {shouldShowCreateButton && (
                <Button
                    variant="ghost"
                    onClick={() => navigate(ROUTES.ADD_KNOWLEDGE_BASE)}
                    className="flex items-center gap-2"
                >
                    <Plus className="size-4" />
                    {t('Create knowledge base')}
                </Button>
            )}
        </header>
    );
}
