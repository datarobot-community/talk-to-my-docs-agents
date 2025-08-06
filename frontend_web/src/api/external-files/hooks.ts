import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getGoogleFiles, getBoxFiles, uploadGoogleFile, uploadBoxFile } from './requests';
import { externalFilesKeys } from './keys';
import { useCurrentUser } from '@/api/auth/hooks';
import { ConnectedSource, ExternalFile } from './types';
import { IIdentity } from '@/api/auth/types';
import { FileSchema } from '../knowledge-bases/types';
import { knowledgeBasesKeys } from '../knowledge-bases/keys';
import { AxiosError } from 'axios';

export const useGoogleFiles = (folderId?: string, enabled: boolean = true) => {
    return useQuery({
        queryKey: externalFilesKeys.googleFolder(folderId),
        queryFn: () => getGoogleFiles(folderId),
        enabled,
    });
};

export const useBoxFiles = (folderId: string = '0', enabled: boolean = true) => {
    return useQuery({
        queryKey: externalFilesKeys.boxFolder(folderId),
        queryFn: () => getBoxFiles(folderId),
        enabled,
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
        mutationFn: async ({ file, source }: { file: ExternalFile; source: 'google' | 'box' }) => {
            if (source === 'google') {
                return await uploadGoogleFile({
                    fileId: file.id,
                    knowledgeBaseUuid: knowledgeBaseUuid,
                });
            } else {
                return await uploadBoxFile({
                    fileId: file.id,
                    knowledgeBaseUuid: knowledgeBaseUuid,
                });
            }
        },

        onSuccess: data => {
            queryClient.invalidateQueries({ queryKey: knowledgeBasesKeys.all });
            onSuccess(data as FileSchema[]);
        },

        onError: error => {
            console.error('External file upload error:', error);
            onError(error as ExternalFileUploadError | AxiosError);
        },
    });
};
