import { useState, useEffect } from 'react';
import { useNavigate, useParams, useLocation } from 'react-router-dom';

import { NewBaseForm } from '@/components/custom/new-knowledge-base-form';
import { TFormData } from '@/types/knowledge-base';
import { ROUTES } from './routes';
import { FileUploader } from '@/components/custom/file-uploader';
import { DATA_VISIBILITY } from '@/state/constants';
import {
    useCreateKnowledgeBase,
    useUpdateKnowledgeBase,
    useGetKnowledgeBase,
    useListFiles,
    KnowledgeBaseCreateRequest,
    KnowledgeBaseUpdateRequest,
} from '@/api/knowledge-bases/hooks';

export const NewKnowledgeBase = () => {
    const { baseUuid } = useParams<{ baseUuid: string }>();
    const location = useLocation();
    const navigate = useNavigate();

    // Determine the mode based on the current path
    const isEditing = location.pathname.includes('/edit/');
    const isManaging = location.pathname.includes('/manage/');
    const knowledgeBaseUuid = baseUuid;

    const [formBase, setFormBase] = useState<TFormData | undefined>();

    const createKnowledgeBaseMutation = useCreateKnowledgeBase();
    const updateKnowledgeBaseMutation = useUpdateKnowledgeBase();
    const { data: existingKnowledgeBase, isLoading: isLoadingKnowledgeBase } = useGetKnowledgeBase(
        knowledgeBaseUuid || ''
    );
    const { data: knowledgeBaseFiles = [] } = useListFiles(knowledgeBaseUuid || '');

    useEffect(() => {
        if (existingKnowledgeBase && (isEditing || isManaging)) {
            setFormBase({
                name: existingKnowledgeBase.title,
                description: existingKnowledgeBase.description,
                visibility: DATA_VISIBILITY.PRIVATE, // Default to private for existing bases
            });
        } else if (!isEditing && !isManaging) {
            // Clear form for new knowledge base creation
            setFormBase(undefined);
        }
    }, [existingKnowledgeBase, isEditing, isManaging]);

    const handleCancel = () => {
        setFormBase(undefined);
        navigate(ROUTES.KNOWLEDGE_BASES);
    };

    const handleSave = async (formData: TFormData) => {
        try {
            if (isEditing && knowledgeBaseUuid) {
                const updateData: KnowledgeBaseUpdateRequest = {
                    title: formData.name,
                    description: formData.description,
                };
                await updateKnowledgeBaseMutation.mutateAsync({
                    baseUuid: knowledgeBaseUuid,
                    data: updateData,
                });
                navigate(ROUTES.KNOWLEDGE_BASES);
            } else if (isManaging) {
                setFormBase(formData);
            } else {
                const createData: KnowledgeBaseCreateRequest = {
                    title: formData.name,
                    description: formData.description,
                    token_count: 0,
                };
                const newBase = await createKnowledgeBaseMutation.mutateAsync(createData);
                // Navigate to file management for the new base
                navigate(`${ROUTES.MANAGE_KNOWLEDGE_BASE}/${newBase.uuid}`);
            }
        } catch (error) {
            console.error('Failed to save base:', error);
        }
    };

    const handleFilesUploaded = () => {
        navigate(ROUTES.KNOWLEDGE_BASES);
    };

    if (isLoadingKnowledgeBase && knowledgeBaseUuid) {
        return (
            <div className="flex justify-center items-center max-h-screen p-6">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 mx-auto mb-4"></div>
                    <p className="text-gray-500">Loading knowledge base...</p>
                </div>
            </div>
        );
    }

    return (
        <div className="flex justify-center max-h-screen">
            <div className="p-6 max-w-2xl w-full">
                {formBase && (isManaging || (!isEditing && !knowledgeBaseUuid)) ? (
                    <>
                        <h2 className="text-xl font-semibold mb-1">{formBase.name}</h2>
                        {formBase.description && (
                            <p className="text-xs text-gray-400 mb-1">{formBase.description}</p>
                        )}
                        <FileUploader
                            onFilesChange={() => {}}
                            progress={0}
                            baseUuid={knowledgeBaseUuid || undefined}
                            onUploadComplete={handleFilesUploaded}
                            existingFiles={knowledgeBaseFiles}
                        />
                    </>
                ) : (
                    <>
                        <h2 className="text-xl font-semibold mb-4">
                            {isEditing ? 'Edit knowledge base' : 'Create a knowledge base'}
                        </h2>
                        <NewBaseForm
                            onSave={handleSave}
                            formValues={formBase}
                            onCancel={handleCancel}
                            isLoading={
                                createKnowledgeBaseMutation.isPending ||
                                updateKnowledgeBaseMutation.isPending
                            }
                        />
                    </>
                )}
            </div>
        </div>
    );
};
