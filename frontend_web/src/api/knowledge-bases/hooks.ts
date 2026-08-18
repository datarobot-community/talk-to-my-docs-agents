import { useState } from 'react';
import { toast } from 'sonner';
import { useMutation, useQueryClient, useQuery } from '@tanstack/react-query';

import {
    uploadFiles,
    deleteFile,
    listKnowledgeBases,
    getKnowledgeBase,
    createKnowledgeBase,
    updateKnowledgeBase,
    deleteKnowledgeBase,
    listFiles,
} from './requests';
import {
    KnowledgeBaseSchema,
    KnowledgeBaseWithContent,
    KnowledgeBaseCreateRequest,
    KnowledgeBaseUpdateRequest,
    FileSchema,
} from './types';

export type {
    KnowledgeBaseSchema,
    KnowledgeBaseWithContent,
    KnowledgeBaseCreateRequest,
    KnowledgeBaseUpdateRequest,
    FileSchema,
};

import { knowledgeBasesKeys } from './keys';
import { AxiosError } from 'axios';

export interface UploadError extends Error {
    responseData?: FileSchema[];
    response?: {
        data: unknown;
    };
    isAxiosError?: boolean;
}

// Knowledge Base hooks
export const useListKnowledgeBases = () => {
    return useQuery({
        queryKey: knowledgeBasesKeys.all,
        queryFn: ({ signal }) => listKnowledgeBases(signal),
        staleTime: 60000, // Use 1 minute, we have invalidate calls when item is changed/deleted
        // Poll while any KB is indexing so the "Indexing…" indicator clears on its
        // own; otherwise rely on staleTime + invalidations.
        refetchInterval: query => {
            const bases = query.state.data ?? [];
            return bases.some(b => b.index_status === 'indexing') ? 4000 : false;
        },
    });
};

export const useGetKnowledgeBase = (knowledgeBaseUuid?: string) => {
    return useQuery({
        queryKey: knowledgeBasesKeys.byId(knowledgeBaseUuid!),
        queryFn: ({ signal }) => getKnowledgeBase(knowledgeBaseUuid!, signal),
        enabled: !!knowledgeBaseUuid,
        staleTime: 60000, // Use 1 minute, we have invalidate calls when item is changed/deleted
    });
};

export const useCreateKnowledgeBase = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (data: KnowledgeBaseCreateRequest) => createKnowledgeBase(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: knowledgeBasesKeys.all });
            toast.success('Knowledge base created successfully');
        },
        onError: error => {
            toast.error(error?.message || 'Failed to create knowledge base');
        },
    });
};

export const useUpdateKnowledgeBase = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ baseUuid, data }: { baseUuid: string; data: KnowledgeBaseUpdateRequest }) =>
            updateKnowledgeBase(baseUuid, data),
        onSuccess: updatedBase => {
            queryClient.invalidateQueries({ queryKey: knowledgeBasesKeys.all });
            queryClient.setQueryData(knowledgeBasesKeys.byId(updatedBase.uuid), updatedBase);
            toast.success('Knowledge base updated successfully');
        },
        onError: error => {
            toast.error(error?.message || 'Failed to update knowledge base');
        },
    });
};

export const useDeleteKnowledgeBase = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (knowledgeBaseUuid: string) => deleteKnowledgeBase(knowledgeBaseUuid),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: knowledgeBasesKeys.all });
        },
    });
};

// File hooks
export const useListFiles = (knowledgeBaseUuid?: string) => {
    return useQuery({
        queryKey: knowledgeBaseUuid
            ? knowledgeBasesKeys.files(knowledgeBaseUuid)
            : knowledgeBasesKeys.allFiles,
        queryFn: ({ signal }) => listFiles(knowledgeBaseUuid, signal),
        staleTime: 60000, // Use 1 minute, we have invalidate calls when item is changed/deleted
    });
};

// Delete file
export const useFileDelete = (knowledgeBaseUuid?: string) => {
    const queryClient = useQueryClient();
    const queryKey = knowledgeBaseUuid
        ? knowledgeBasesKeys.files(knowledgeBaseUuid)
        : knowledgeBasesKeys.allFiles;

    return useMutation({
        mutationFn: ({ fileUuid }: { fileUuid: string }) => deleteFile(fileUuid),
        onMutate: async ({ fileUuid }) => {
            await queryClient.cancelQueries({ queryKey });

            queryClient.setQueryData<FileSchema[]>(queryKey, old =>
                (old || []).filter(file => file.uuid !== fileUuid)
            );
        },
        onSuccess: () => {
            toast.success('File has been successfully removed');
        },
        onError: error => {
            toast.error(error?.message || 'Failed to delete file');
        },
        onSettled: () => {
            queryClient.invalidateQueries({ queryKey });
            queryClient.invalidateQueries({
                queryKey: knowledgeBasesKeys.all,
            });
        },
    });
};

// Upload hook
export const useFileUploadMutation = ({
    onSuccess,
    onError,
    baseUuid,
}: {
    onSuccess: (data: FileSchema[]) => void;
    onError: (error: UploadError | AxiosError) => void;
    baseUuid?: string;
}) => {
    const [progress, setProgress] = useState(0);
    const queryClient = useQueryClient();

    const mutation = useMutation({
        mutationFn: async ({ files }: { files: File[] }) => {
            return await uploadFiles({
                files,
                knowledgeBaseUuid: baseUuid,
                onUploadProgress: progressEvent => {
                    if (progressEvent.total) {
                        const prg = Math.round((progressEvent.loaded * 100) / progressEvent.total);
                        setProgress(prg);
                    }
                },
            });
        },
        onSuccess: data => {
            const queryKey = baseUuid
                ? knowledgeBasesKeys.files(baseUuid)
                : knowledgeBasesKeys.allFiles;
            queryClient.invalidateQueries({ queryKey });
            queryClient.invalidateQueries({
                queryKey: knowledgeBasesKeys.all,
            });
            onSuccess(data as FileSchema[]);
        },
        onError: (error: UploadError | AxiosError) => {
            const uploadError = error as UploadError;

            if (uploadError.responseData) {
                uploadError.response = { data: uploadError.responseData };
            } else if (
                'isAxiosError' in error &&
                error.isAxiosError &&
                (error as AxiosError).response
            ) {
                const axiosError = error as AxiosError;
                uploadError.response = {
                    data: axiosError.response?.data,
                };
            }

            onError(uploadError);
        },
    });

    return { ...mutation, progress };
};
