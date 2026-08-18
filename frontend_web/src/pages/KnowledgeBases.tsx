import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Edit, Trash2, FileText, Calendar, EllipsisVertical } from 'lucide-react';

import noBasesPreview from '@/assets/no_bases_preview.svg';
import noBasesPreviewLight from '@/assets/no_bases_preview_light.svg';
import { Button } from '@/components/ui/button.tsx';
import { Badge } from '@/components/ui/badge';
import { Spinner } from '@/components/ui/spinner';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { ROUTES } from './routes';
import {
    useListKnowledgeBases,
    useDeleteKnowledgeBase,
    KnowledgeBaseSchema,
} from '@/api/knowledge-bases/hooks';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
    Card,
    CardHeader,
    CardTitle,
    CardDescription,
    CardAction,
    CardContent,
    CardFooter,
} from '@/components/ui/card';
import { Heading } from '@/components/ui/heading';
import { useTheme } from '@/theme/theme-provider';
import { useTranslation } from '@/lib/i18n';
import { isVdbEnabled } from '@/lib/ttmdocs-utils';

export const KnowledgeBases = () => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const { data: knowledgeBase = [], isLoading, error } = useListKnowledgeBases();
    const deleteBaseMutation = useDeleteKnowledgeBase();
    const [deletingBaseId, setDeletingBaseId] = useState<string | null>(null);
    // Only surface the search-mode label / indexing indicator when the feature is on.
    const vdbEnabled = isVdbEnabled();
    const { theme } = useTheme();
    const handleDeleteBase = async (baseUuid: string) => {
        if (
            confirm(
                t(
                    'Are you sure you want to delete this knowledge base? This action cannot be undone.'
                )
            )
        ) {
            setDeletingBaseId(baseUuid);
            try {
                await deleteBaseMutation.mutateAsync(baseUuid);
            } catch (error) {
                console.error(t('Failed to delete base:'), error);
            } finally {
                setDeletingBaseId(null);
            }
        }
    };

    const formatDate = (dateString: string) => {
        return new Date(dateString).toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
        });
    };

    if (isLoading) {
        return (
            <div className="flex max-h-screen items-center justify-center p-6">
                <div className="text-center">
                    <div className="mx-auto mb-4 size-8 animate-spin rounded-full border-b-2"></div>
                    <p className="body-secondary">Loading knowledge bases...</p>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex max-h-screen items-center justify-center p-6">
                <div className="text-center">
                    <p className="text-destructive mb-4">{t('Failed to load knowledge bases')}</p>
                    <Button onClick={() => window.location.reload()}>{t('Retry')}</Button>
                </div>
            </div>
        );
    }

    if (knowledgeBase.length === 0) {
        return (
            <div data-testid="knowledge-empty-state" className="flex max-h-screen justify-center">
                <div className="flex max-h-screen w-full max-w-2xl flex-col items-center justify-center p-6 pt-48">
                    <img
                        src={theme === 'light' ? noBasesPreviewLight : noBasesPreview}
                        alt="No knowledge bases yet"
                        className="mx-auto mb-4 size-48"
                    />
                    <h2 className="mb-4 text-xl font-semibold">{t('No knowledge bases yet')}</h2>
                    <p className="body-secondary">
                        {t(
                            'Create a knowledge base to group documents by topic, team, or use case.'
                        )}
                    </p>
                    <p className="body-secondary mb-6">
                        {t(
                            'Once uploaded, you can search, summarize, and chat with them using AI.'
                        )}
                    </p>

                    <Button
                        data-testid="create-knowledge-base-button"
                        onClick={() => navigate(ROUTES.ADD_KNOWLEDGE_BASE)}
                        className="flex h-9 cursor-pointer"
                    >
                        {t('Create knowledge base')}
                    </Button>
                </div>
            </div>
        );
    }

    return (
        <div className="mx-auto w-full max-w-6xl p-6">
            <div className="mb-6 flex items-center justify-between">
                <div>
                    <Heading level={2}>{t('Knowledge Bases')}</Heading>
                    <p className="body-secondary">
                        {t('Manage your document collections and upload files to knowledge bases')}
                    </p>
                </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {knowledgeBase.map((base: KnowledgeBaseSchema) => (
                    <Card data-testid="knowledge-base-card" className="h-full" key={base.uuid}>
                        <CardHeader>
                            <TooltipProvider>
                                <Tooltip>
                                    <TooltipTrigger asChild>
                                        <CardTitle
                                            data-testid="knowledge-base-title"
                                            className="line-clamp-2 wrap-anywhere"
                                        >
                                            {base.title}
                                        </CardTitle>
                                    </TooltipTrigger>
                                    <TooltipContent className="max-w-xs wrap-break-word whitespace-normal">
                                        <p>{base.title}</p>
                                    </TooltipContent>
                                </Tooltip>
                            </TooltipProvider>
                            <TooltipProvider>
                                <Tooltip>
                                    <TooltipTrigger asChild>
                                        <CardDescription
                                            data-testid="knowledge-base-description"
                                            className="line-clamp-3 wrap-anywhere"
                                        >
                                            {base.description}
                                        </CardDescription>
                                    </TooltipTrigger>
                                    <TooltipContent className="max-w-xs wrap-break-word whitespace-normal">
                                        {base.description}
                                    </TooltipContent>
                                </Tooltip>
                            </TooltipProvider>
                            {vdbEnabled && (
                                <div className="mt-2 flex flex-wrap items-center gap-2">
                                    <Badge
                                        data-testid="kb-mode-badge"
                                        type="outline"
                                        variant={
                                            base.retrieval_mode === 'semantic' ? 'info' : 'default'
                                        }
                                    >
                                        {base.retrieval_mode === 'semantic'
                                            ? t('Semantic search')
                                            : t('Keyword match')}
                                    </Badge>
                                    {base.retrieval_mode === 'semantic' &&
                                        base.index_status === 'indexing' && (
                                            <Badge data-testid="kb-status-badge" variant="warning">
                                                <Spinner className="mr-1 size-3" />
                                                {t('Indexing…')}
                                            </Badge>
                                        )}
                                    {base.retrieval_mode === 'semantic' &&
                                        base.index_status === 'ready' && (
                                            <Badge data-testid="kb-status-badge" variant="success">
                                                {t('Ready')}
                                            </Badge>
                                        )}
                                    {base.retrieval_mode === 'semantic' &&
                                        base.index_status === 'failed' && (
                                            <TooltipProvider>
                                                <Tooltip>
                                                    <TooltipTrigger asChild>
                                                        <Badge
                                                            data-testid="kb-status-badge"
                                                            variant="destructive"
                                                        >
                                                            {t('Indexing failed')}
                                                        </Badge>
                                                    </TooltipTrigger>
                                                    {base.last_error && (
                                                        <TooltipContent className="max-w-xs wrap-break-word whitespace-normal">
                                                            {base.last_error}
                                                        </TooltipContent>
                                                    )}
                                                </Tooltip>
                                            </TooltipProvider>
                                        )}
                                </div>
                            )}
                            <CardAction>
                                <DropdownMenu>
                                    <TooltipProvider>
                                        <Tooltip>
                                            <TooltipTrigger asChild>
                                                <DropdownMenuTrigger asChild>
                                                    <Button
                                                        disabled={!base.can_edit}
                                                        data-testid="knowledge-base-menu-button"
                                                        variant="ghost"
                                                        size="sm"
                                                    >
                                                        <span className="sr-only">
                                                            {t('Open menu')}
                                                        </span>
                                                        <EllipsisVertical />
                                                    </Button>
                                                </DropdownMenuTrigger>
                                            </TooltipTrigger>
                                            {!base.can_edit && (
                                                <TooltipContent className="max-w-xs wrap-break-word whitespace-normal">
                                                    {t(
                                                        'This knowledge base is public and cannot be edited.'
                                                    )}
                                                </TooltipContent>
                                            )}
                                        </Tooltip>
                                    </TooltipProvider>
                                    <DropdownMenuContent>
                                        <DropdownMenuItem
                                            data-testid="knowledge-base-edit-button"
                                            onClick={() =>
                                                navigate(
                                                    `${ROUTES.EDIT_KNOWLEDGE_BASE}/${base.uuid}`
                                                )
                                            }
                                        >
                                            <Edit />
                                            {t('Edit')}
                                        </DropdownMenuItem>
                                        <DropdownMenuItem
                                            data-testid="knowledge-base-delete-button"
                                            onClick={() => handleDeleteBase(base.uuid)}
                                            variant="destructive"
                                            disabled={deletingBaseId === base.uuid}
                                        >
                                            <Trash2 />
                                            {deletingBaseId === base.uuid
                                                ? t('Deleting...')
                                                : t('Delete')}
                                        </DropdownMenuItem>
                                    </DropdownMenuContent>
                                </DropdownMenu>
                            </CardAction>
                        </CardHeader>

                        <CardContent className="mn-label space-y-2">
                            <div className="flex items-center gap-2">
                                <FileText className="size-4" />
                                <span data-testid="knowledge-base-file-count">
                                    {' '}
                                    {t('{{files}} file • {{tokens}} tokens', {
                                        files: base.files.length,
                                        tokens: base.token_count.toLocaleString(),
                                        count: base.files.length,
                                        plural: '{{files}} files • {{tokens}} tokens',
                                    })}
                                </span>
                            </div>
                            <div className="flex items-center gap-2">
                                <Calendar className="size-4" />
                                <span>
                                    {t('Created {{date}}', { date: formatDate(base.created_at) })}
                                </span>
                            </div>
                        </CardContent>

                        {base.can_edit && (
                            <CardFooter>
                                <Button
                                    variant="secondary"
                                    size="sm"
                                    className="w-full"
                                    onClick={() =>
                                        navigate(`${ROUTES.MANAGE_KNOWLEDGE_BASE}/${base.uuid}`)
                                    }
                                >
                                    {t('Manage Files')}
                                </Button>
                            </CardFooter>
                        )}
                    </Card>
                ))}
            </div>
        </div>
    );
};
