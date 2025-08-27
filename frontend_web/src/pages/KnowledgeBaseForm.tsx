import { useState, useEffect } from 'react';
import { useNavigate, useParams, useLocation } from 'react-router-dom';

import { KnowledgeBaseForm } from '@/components/custom/knowledge-base-form';
import { TFormData } from '@/types/knowledge-base';
import { ROUTES } from './routes';
import { FileUploader } from '@/components/custom/file-uploader';
import {
    useCreateKnowledgeBase,
    useUpdateKnowledgeBase,
    useGetKnowledgeBase,
    useListFiles,
    KnowledgeBaseCreateRequest,
    KnowledgeBaseUpdateRequest,
    useFileDelete,
} from '@/api/knowledge-bases/hooks';

export const KnowledgeBaseFormPage = () => {
    const { baseUuid } = useParams<{ baseUuid: string }>();
    const location = useLocation();
    const navigate = useNavigate();

    // Determine the mode based on the current path
    const isEditing = location.pathname.includes('/edit');
    const isManaging = location.pathname.includes('/manage');
    const knowledgeBaseUuid = baseUuid;

    const [formBase, setFormBase] = useState<TFormData | undefined>();

    const createKnowledgeBaseMutation = useCreateKnowledgeBase();
    const updateKnowledgeBaseMutation = useUpdateKnowledgeBase();
    const { data: existingKnowledgeBase, isLoading: isLoadingKnowledgeBase } = useGetKnowledgeBase(
        knowledgeBaseUuid || ''
    );
    const deleteFileMutation = useFileDelete(knowledgeBaseUuid);
    const { data: knowledgeBaseFiles = [] } = useListFiles(knowledgeBaseUuid || '');

    useEffect(() => {
        if (existingKnowledgeBase && (isEditing || isManaging)) {
            setFormBase({
                name: existingKnowledgeBase.title,
                description: existingKnowledgeBase.description,
                is_public: existingKnowledgeBase.is_public, // Default to private for existing bases
            });
        } else if (!isEditing && !isManaging) {
            // Clear form for new forecast view creation
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
                    is_public: formData.is_public,
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
                    is_public: formData.is_public,
                };
                const newBase = await createKnowledgeBaseMutation.mutateAsync(createData);
                // Navigate to file management for the new base
                navigate(`${ROUTES.MANAGE_KNOWLEDGE_BASE}/${newBase.uuid}`);
            }
        } catch (error) {
            console.error('Failed to save base:', error);
        }
    };

    const handleFileDelete = (fileUuid: string) => {
        deleteFileMutation.mutate({ fileUuid });
    };

    if (isLoadingKnowledgeBase && knowledgeBaseUuid) {
        return (
            <div className="flex justify-center items-center max-h-screen p-6">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 mx-auto mb-4"></div>
                    <p className="text-gray-500">Loading forecast view...</p>
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
                            onDeleteFile={handleFileDelete}
                            baseUuid={knowledgeBaseUuid || undefined}
                            existingFiles={knowledgeBaseFiles}
                        />
                    </>
                ) : (
                    <>
                        <h2 className="text-xl font-semibold mb-4">
                            {isEditing ? 'Edit Forecast View' : 'Create a Forecast View'}
                        </h2>
                        <KnowledgeBaseForm
                            onSave={handleSave}
                            formValues={formBase}
                            onCancel={handleCancel}
                            isLoading={
                                createKnowledgeBaseMutation.isPending ||
                                updateKnowledgeBaseMutation.isPending
                            }
                            isEditing={isEditing}
                        />
                    </>
                )}
            </div>
        </div>
    );
};
