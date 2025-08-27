import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Edit, Trash2, FileText, Calendar } from 'lucide-react';

import noBasesPreview from '@/assets/no_bases_preview.svg';
import { Button } from '@/components/ui/button.tsx';
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

export const KnowledgeBases = () => {
    const navigate = useNavigate();
    const { data: bases = [], isLoading, error } = useListKnowledgeBases();
    const deleteBaseMutation = useDeleteKnowledgeBase();
    const [deletingBaseId, setDeletingBaseId] = useState<string | null>(null);

    // Only show bases the user can edit on this page
    const editableBases = bases.filter(base => base.can_edit);

    const handleDeleteBase = async (baseUuid: string) => {
        if (
            confirm(
                'Are you sure you want to delete this forecast view? This action cannot be undone.'
            )
        ) {
            setDeletingBaseId(baseUuid);
            try {
                await deleteBaseMutation.mutateAsync(baseUuid);
            } catch (error) {
                console.error('Failed to delete base:', error);
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
            <div className="flex justify-center items-center max-h-screen p-6">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 mx-auto mb-4"></div>
                    <p className="text-gray-500">Loading forecast views...</p>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex justify-center items-center max-h-screen p-6">
                <div className="text-center">
                    <p className="text-red-500 mb-4">Failed to load forecast views</p>
                    <Button onClick={() => window.location.reload()}>Retry</Button>
                </div>
            </div>
        );
    }

    if (editableBases.length === 0) {
        return (
            <div data-testid="knowledge-empty-state" className="flex justify-center max-h-screen">
                <div className="p-6 pt-48 max-w-2xl w-full items-center flex-col justify-center flex max-h-screen">
                    <img
                        src={noBasesPreview}
                        alt="No forecast views yet"
                        className="w-48 h-48 mx-auto mb-4"
                    />
                    <h2 className="text-xl font-semibold mb-4">No forecast views yet</h2>
                    <p className="text-gray-500">
                        Create a forecast view to group documents by topic, team, or use case.
                    </p>
                    <p className="text-gray-500 mb-6">
                        Once uploaded, you can search, summarize, and chat with them using AI.
                    </p>

                    <Button
                        data-testid="create-knowledge-base-button"
                        onClick={() => navigate(ROUTES.ADD_KNOWLEDGE_BASE)}
                        className="h-9 flex cursor-pointer"
                    >
                        Create forecast view
                    </Button>
                </div>
            </div>
        );
    }

    return (
        <div className="p-6 max-w-6xl mx-auto">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h1 className="text-2xl font-bold text-white">Forecast Views</h1>
                    <p className="text-gray-400 mt-1">
                        Manage your document collections and upload files to forecast views
                    </p>
                </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {editableBases.map((base: KnowledgeBaseSchema) => (
                    <div
                        data-testid="knowledge-base-card"
                        key={base.uuid}
                        className="border border-gray-700 rounded-lg p-6 hover:shadow-lg transition-shadow bg-card hover:bg-gray-750 flex flex-col h-full"
                    >
                        <div className="flex justify-between items-start mb-4">
                            <div className="flex-1">
                                <h3
                                    data-testid="knowledge-base-title"
                                    className="font-semibold text-lg mb-2 line-clamp-2 text-white"
                                >
                                    {base.title}
                                </h3>
                                <p
                                    data-testid="knowledge-base-description"
                                    className="text-gray-300 text-sm line-clamp-3 mb-3"
                                >
                                    {base.description}
                                </p>
                            </div>
                            <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                    <Button
                                        data-testid="knowledge-base-menu-button"
                                        variant="ghost"
                                        size="sm"
                                        className="h-8 w-8 p-0 text-gray-400 hover:text-white hover:bg-gray-700"
                                    >
                                        <span className="sr-only">Open menu</span>
                                        <svg
                                            className="h-4 w-4"
                                            fill="currentColor"
                                            viewBox="0 0 20 20"
                                        >
                                            <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
                                        </svg>
                                    </Button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent
                                    align="end"
                                    className="bg-gray-800 border-gray-700"
                                >
                                    <DropdownMenuItem
                                        data-testid="knowledge-base-edit-button"
                                        onClick={() =>
                                            navigate(`${ROUTES.EDIT_KNOWLEDGE_BASE}/${base.uuid}`)
                                        }
                                        className="cursor-pointer text-gray-300 hover:text-white hover:bg-gray-700"
                                    >
                                        <Edit className="h-4 w-4 mr-2" />
                                        Edit
                                    </DropdownMenuItem>
                                    <DropdownMenuItem
                                        data-testid="knowledge-base-delete-button"
                                        onClick={() => handleDeleteBase(base.uuid)}
                                        className="cursor-pointer text-red-400 hover:text-red-300 hover:bg-gray-700"
                                        disabled={deletingBaseId === base.uuid}
                                    >
                                        <Trash2 className="h-4 w-4 mr-2" />
                                        {deletingBaseId === base.uuid ? 'Deleting...' : 'Delete'}
                                    </DropdownMenuItem>
                                </DropdownMenuContent>
                            </DropdownMenu>
                        </div>

                        <div className="space-y-2 text-sm text-gray-400 flex-grow">
                            <div className="flex items-center gap-2">
                                <FileText className="h-4 w-4" />
                                <span data-testid="knowledge-base-file-count">
                                    {base.files.length} file{base.files.length !== 1 ? 's' : ''} •{' '}
                                    {base.token_count.toLocaleString()} tokens
                                </span>
                            </div>
                            <div className="flex items-center gap-2">
                                <Calendar className="h-4 w-4" />
                                <span>Created {formatDate(base.created_at)}</span>
                            </div>
                        </div>

                        <div className="mt-4 pt-4 border-t border-gray-700">
                            <Button
                                variant="outline"
                                size="sm"
                                className="w-full border-gray-600 text-gray-300 hover:text-white hover:bg-gray-700 hover:border-gray-500"
                                onClick={() =>
                                    navigate(`${ROUTES.MANAGE_KNOWLEDGE_BASE}/${base.uuid}`)
                                }
                            >
                                Manage Files
                            </Button>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};
