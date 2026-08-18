import { useState, useEffect } from 'react';
import { useNavigate, useParams, useLocation } from 'react-router-dom';

import { KnowledgeBaseForm } from '@/components/custom/knowledge-base-form';
import { TFormData } from '@/types';
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
import { Spinner } from '@/components/ui/spinner';
import { Heading } from '@/components/ui/heading';
import { useTranslation } from '@/lib/i18n';

export const KnowledgeBaseFormPage = () => {
    const { baseUuid } = useParams<{ baseUuid: string }>();
    const location = useLocation();
    const navigate = useNavigate();
    const { t } = useTranslation();
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
                retrieval_mode: existingKnowledgeBase.retrieval_mode,
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
                    is_public: formData.is_public,
                    retrieval_mode: formData.retrieval_mode,
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
                    retrieval_mode: formData.retrieval_mode,
                };
                const newBase = await createKnowledgeBaseMutation.mutateAsync(createData);
                // Navigate to file management for the new base
                navigate(`${ROUTES.MANAGE_KNOWLEDGE_BASE}/${newBase.uuid}`);
            }
        } catch (error) {
            console.error(t('Failed to save base:'), error);
        }
    };

    const handleFileDelete = (fileUuid: string) => {
        return deleteFileMutation.mutateAsync({ fileUuid });
    };

    if (isLoadingKnowledgeBase && knowledgeBaseUuid) {
        return (
            <div className="flex flex-row items-center justify-center gap-2 p-6">
                <Spinner className="size-8" />
                <p>{t('Loading knowledge base...')}</p>
            </div>
        );
    }

    return (
        <div className="flex max-h-screen justify-center">
            <div className="w-full max-w-2xl p-6">
                {formBase && (isManaging || (!isEditing && !knowledgeBaseUuid)) ? (
                    <>
                        <Heading level={2} className="mb-1">
                            {formBase.name}
                        </Heading>
                        {formBase.description && (
                            <p className="caption-01 mb-1">{formBase.description}</p>
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
                        <h2 className="mb-4 text-xl font-semibold">
                            {isEditing ? t('Edit Knowledge Base') : t('Create a Knowledge Base')}
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
