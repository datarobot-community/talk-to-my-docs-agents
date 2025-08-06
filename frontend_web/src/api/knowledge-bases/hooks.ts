import { useState } from 'react';
import { useMutation, useQueryClient, useQuery } from '@tanstack/react-query';

import {
    uploadFiles,
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
    });
};

export const useGetKnowledgeBase = (knowledgeBaseUuid: string) => {
    return useQuery({
        queryKey: knowledgeBasesKeys.byId(knowledgeBaseUuid),
        queryFn: ({ signal }) => getKnowledgeBase(knowledgeBaseUuid, signal),
        enabled: !!knowledgeBaseUuid,
    });
};

export const useCreateKnowledgeBase = () => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (data: KnowledgeBaseCreateRequest) => createKnowledgeBase(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: knowledgeBasesKeys.all });
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
            const response = await uploadFiles({
                files,
                knowledgeBaseUuid: baseUuid,
                onUploadProgress: progressEvent => {
                    if (progressEvent.total) {
                        const prg = Math.round((progressEvent.loaded * 100) / progressEvent.total);
                        setProgress(prg);
                    }
                },
            });

            return response;
        },

        onSuccess: data => {
            queryClient.invalidateQueries({ queryKey: knowledgeBasesKeys.all });
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
        onSettled: () => queryClient.invalidateQueries({ queryKey: knowledgeBasesKeys.all }),
    });

    return { ...mutation, progress };
};
