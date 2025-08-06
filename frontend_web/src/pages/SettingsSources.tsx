import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useOauthProviders, useAuthorizeProvider } from '@/api/oauth/hooks';
import { PATHS } from '@/constants/paths';
import { useState, useEffect } from 'react';
import { useCurrentUser } from '@/api/auth/hooks';
import { CheckCircle2 } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Skeleton } from '@/components/ui/skeleton';
import { getBaseUrl } from '@/lib/utils.ts';

export const SettingsSources = () => {
    const {
        data: providers = [],
        isLoading,
        isError: isErrorFetchingProviders,
    } = useOauthProviders();
    const { mutate: authorizeProvider, isPending } = useAuthorizeProvider();
    const [connectingId, setConnectingId] = useState<string | null>(null);
    const { data: currentUser } = useCurrentUser();

    const connectedIds = new Set(currentUser?.identities.map(id => id.provider_id) ?? []);
    let baseUrl = getBaseUrl();
    if (baseUrl.endsWith('/')) {
        baseUrl = baseUrl.slice(0, -1);
    }
    const redirectUri = `${window.location.origin}${baseUrl}${PATHS.OAUTH_CB}`;
    const location = useLocation();
    const navigate = useNavigate();
    const [oauthError, setOauthError] = useState<string | null>(null);

    useEffect(() => {
        const params = new URLSearchParams(location.search);
        const err = params.get('error');
        if (err) {
            setOauthError(err);
            params.delete('error');
            navigate({ pathname: location.pathname, search: params.toString() }, { replace: true });
        }
    }, [location, navigate]);

    return (
        <ScrollArea className="flex-1 p-8">
            <h2 className="text-xl font-semibold mb-6">Connected sources</h2>
            {oauthError && <p className="text-destructive mb-4">Failed to connect: {oauthError}</p>}

            {isLoading && (
                <div className="space-y-4">
                    <Skeleton key={0} className="h-20 w-full rounded-md" />
                    <Skeleton key={1} className="h-20 w-full rounded-md" />
                    <Skeleton key={2} className="h-20 w-full rounded-md" />
                </div>
            )}

            {isErrorFetchingProviders && (
                <p className="text-destructive">Failed to load connected sources.</p>
            )}

            {!isLoading && !isErrorFetchingProviders && providers.length === 0 && (
                <p className="text-muted-foreground">No sources available.</p>
            )}

            {!isLoading && providers.length > 0 && (
                <div className="divide-y divide-border">
                    {providers.map(provider => (
                        <div key={provider.id} className="flex items-center justify-between py-4">
                            <div>
                                <p className="font-medium">
                                    {provider.type
                                        ? provider.type.charAt(0).toUpperCase() +
                                          provider.type.slice(1)
                                        : provider.name || provider.id}
                                </p>
                                {/* placeholder description */}
                            </div>
                            {connectedIds.has(provider.id) ? (
                                <span className="flex items-center gap-1 text-green-500 font-medium">
                                    <CheckCircle2 className="w-4 h-4" /> Connected
                                </span>
                            ) : (
                                <Button
                                    variant="outline"
                                    disabled={isPending && connectingId === provider.id}
                                    onClick={() => {
                                        setConnectingId(provider.id);
                                        authorizeProvider(
                                            {
                                                providerId: provider.id,
                                                redirect_uri: redirectUri,
                                            },
                                            {
                                                onSuccess: ({ redirect_url }) => {
                                                    window.location.href = redirect_url;
                                                },
                                                onError: () => {
                                                    setConnectingId(null);
                                                },
                                            }
                                        );
                                    }}
                                >
                                    Connect
                                </Button>
                            )}
                        </div>
                    ))}
                </div>
            )}
        </ScrollArea>
    );
};
