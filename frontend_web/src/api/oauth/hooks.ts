import { useMutation, useQuery } from '@tanstack/react-query';
import { listProviders, authorizeProvider } from './requests';
import { oauthKeys } from './keys';
import { IOAuthProvider, IOAuthAuthorizeResponse } from './types';
import apiClient from '../apiClient';

export const useOauthProviders = () => {
    return useQuery<IOAuthProvider[], Error>({
        queryKey: oauthKeys.all,
        queryFn: () => listProviders(),
    });
};

export const useAuthorizeProvider = () => {
    return useMutation<
        IOAuthAuthorizeResponse,
        Error,
        { providerId: string; redirect_uri: string }
    >({
        mutationFn: ({ providerId, redirect_uri }) =>
            authorizeProvider(providerId, { redirect_uri }),
    });
};

export const useOauthCallback = (search: string, enabled: boolean) => {
    return useQuery({
        queryKey: ['oauthCallback', search],
        queryFn: () => apiClient.get(`/v1/oauth/callback/${search}`),
        enabled,
        retry: false,
    });
};
