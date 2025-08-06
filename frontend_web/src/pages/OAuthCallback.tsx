import { useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useOauthCallback } from '@/api/oauth/hooks';
import { PATHS } from '@/constants/paths';

const OAuthCallback = () => {
    const navigate = useNavigate();
    const location = useLocation();

    const buildErrorUrl = (e: string) => `${PATHS.SETTINGS.SOURCES}?error=${e}`;

    const params = new URLSearchParams(location.search);
    const providerError = params.get('error');

    useEffect(() => {
        // redirect to the page where we will show error, no need to send it to backend
        if (providerError) {
            navigate(buildErrorUrl(providerError), { replace: true });
        }
    }, [providerError, navigate]);

    const state = params.get('state');

    const { isSuccess, isError } = useOauthCallback(location.search, !!state && !providerError);

    useEffect(() => {
        if (isSuccess) navigate(PATHS.SETTINGS.SOURCES, { replace: true });
        if (isError) navigate(buildErrorUrl('oauth_failed'), { replace: true });
    }, [isSuccess, isError, navigate]);

    return <div className="flex items-center justify-center h-full">Finishing sign-in…</div>;
};

export default OAuthCallback;
