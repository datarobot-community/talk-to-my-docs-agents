import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
    getGoogleFiles,
    getBoxFiles,
    getSharePointFiles,
    uploadGoogleFile,
    uploadBoxFile,
    uploadSharePointFile,
} from './requests';
import { externalFilesKeys } from './keys';
import { useCurrentUser } from '@/api/auth/hooks';
import { ConnectedSource, ExternalFile, SharePointNavState } from './types';
import { IIdentity } from '@/api/auth/types';
import { FileSchema } from '../knowledge-bases/types';
import { knowledgeBasesKeys } from '../knowledge-bases/keys';
import { AxiosError } from 'axios';
import { authKeys } from '../auth/hooks';

export const useGoogleFiles = (folderId?: string, enabled: boolean = true) => {
    const queryClient = useQueryClient();
    return useQuery({
        queryKey: externalFilesKeys.googleFolder(folderId),
        queryFn: () => getGoogleFiles(folderId),
        enabled,
        retry: (failureCount, error) => {
            // Don't retry on authentication errors (401) or authorization errors (403)
            if (error && typeof error === 'object' && 'response' in error) {
                const axiosError = error as AxiosError;
                if (axiosError.response?.status === 401 || axiosError.response?.status === 403) {
                    queryClient.invalidateQueries({ queryKey: authKeys.currentUser });
                    return false;
                }
            }
            // For other errors, retry up to 2 times
            return failureCount < 2;
        },
        retryDelay: attemptIndex => Math.min(1000 * 2 ** attemptIndex, 30000),
    });
};

export const useBoxFiles = (folderId: string = '0', enabled: boolean = true) => {
    const queryClient = useQueryClient();
    return useQuery({
        queryKey: externalFilesKeys.boxFolder(folderId),
        queryFn: () => getBoxFiles(folderId),
        enabled,
        retry: (failureCount, error) => {
            // Don't retry on authentication errors (401) or authorization errors (403)
            if (error && typeof error === 'object' && 'response' in error) {
                const axiosError = error as AxiosError;
                if (axiosError.response?.status === 401 || axiosError.response?.status === 403) {
                    queryClient.invalidateQueries({ queryKey: authKeys.currentUser });
                    return false;
                }
            }
            // For other errors, retry up to 2 times
            return failureCount < 2;
        },
        retryDelay: attemptIndex => Math.min(1000 * 2 ** attemptIndex, 30000),
    });
};

export const useSharePointFiles = (nav: SharePointNavState = {}, enabled: boolean = true) => {
    const queryClient = useQueryClient();
    return useQuery({
        queryKey: externalFilesKeys.sharepointFolder(nav.siteId, nav.driveId, nav.folderId),
        queryFn: () => getSharePointFiles(nav),
        enabled,
        retry: (failureCount, error) => {
            if (error && typeof error === 'object' && 'response' in error) {
                const axiosError = error as AxiosError;
                if (axiosError.response?.status === 401 || axiosError.response?.status === 403) {
                    queryClient.invalidateQueries({ queryKey: authKeys.currentUser });
                    return false;
                }
            }
            return failureCount < 2;
        },
        retryDelay: attemptIndex => Math.min(1000 * 2 ** attemptIndex, 30000),
    });
};

// Hook to get available connected sources based on user identities
export const useConnectedSources = () => {
    const { data: user } = useCurrentUser();

    const connectedSources: ConnectedSource[] = [];

    if (user?.identities) {
        const hasGoogle = user.identities.some((identity: IIdentity) =>
            identity.provider_type?.toLowerCase().includes('google')
        );
        const hasBox = user.identities.some((identity: IIdentity) =>
            identity.provider_type?.toLowerCase().includes('box')
        );
        const hasSharePoint = user.identities.some((identity: IIdentity) =>
            identity.provider_type?.toLowerCase().includes('sharepoint')
        );

        if (hasGoogle) {
            connectedSources.push({
                id: 'google',
                name: 'Google Drive',
                type: 'google',
                isConnected: true,
            });
        }

        if (hasBox) {
            connectedSources.push({
                id: 'box',
                name: 'Box',
                type: 'box',
                isConnected: true,
            });
        }

        if (hasSharePoint) {
            connectedSources.push({
                id: 'sharepoint',
                name: 'SharePoint',
                type: 'sharepoint',
                isConnected: true,
            });
        }
    }

    return { connectedSources, hasConnectedSources: connectedSources.length > 0 };
};

export interface ExternalFileUploadError extends Error {
    responseData?: FileSchema[];
    response?: {
        data: unknown;
    };
    isAxiosError?: boolean;
}

export const useExternalFileUploadMutation = ({
    onSuccess,
    onError,
    knowledgeBaseUuid: knowledgeBaseUuid,
}: {
    onSuccess: (data: FileSchema[]) => void;
    onError: (error: ExternalFileUploadError | AxiosError) => void;
    knowledgeBaseUuid?: string;
}) => {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({
            file,
            source,
        }: {
            file: ExternalFile;
            source: 'google' | 'box' | 'sharepoint';
        }) => {
            if (source === 'google') {
                return await uploadGoogleFile({
                    fileId: file.id,
                    knowledgeBaseUuid: knowledgeBaseUuid,
                });
            } else if (source === 'box') {
                return await uploadBoxFile({
                    fileId: file.id,
                    knowledgeBaseUuid: knowledgeBaseUuid,
                });
            } else {
                return await uploadSharePointFile({
                    fileId: file.id,
                    knowledgeBaseUuid: knowledgeBaseUuid,
                });
            }
        },

        onSuccess: data => {
            queryClient.invalidateQueries({ queryKey: knowledgeBasesKeys.all });
            queryClient.invalidateQueries({ queryKey: knowledgeBasesKeys.allFiles });
            onSuccess(data as FileSchema[]);
        },

        onError: error => {
            console.error('External file upload error:', error);
            onError(error as ExternalFileUploadError | AxiosError);
        },
    });
};
