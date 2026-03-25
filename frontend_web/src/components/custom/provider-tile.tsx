import { Check, AlertCircle, Link as LinkIcon, Pencil } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useTranslation } from '@/lib/i18n';
import gdriveIcon from '@/assets/GoogleDriveLogo.svg';
import boxIcon from '@/assets/BoxLogo.svg';
import sharepointIcon from '@/assets/SharePointLogo.svg';
import { IOAuthProviderType } from '@/api/oauth/types';
import { Card, CardFooter, CardContent, CardHeader } from '../ui/card';

export type ProviderStatus = 'connected' | 'warning' | 'disconnected';

interface ProviderTileProps {
    type: IOAuthProviderType;
    status: ProviderStatus;
    onConnect?: () => void;
    onEdit?: () => void;
    isConnecting?: boolean;
}

const PROVIDER_LOGOS: Record<IOAuthProviderType, string> = {
    google: gdriveIcon,
    box: boxIcon,
    sharepoint: sharepointIcon,
};

export function ProviderTile({
    type,
    status,
    onConnect,
    onEdit,
    isConnecting = false,
}: ProviderTileProps) {
    const { t } = useTranslation();
    const PROVIDER_DISPLAY_NAMES: Record<IOAuthProviderType, string> = {
        google: t('Google Drive'),
        box: t('Box'),
        sharepoint: t('SharePoint'),
    };

    const STATUS_CONFIG = {
        connected: {
            borderClass: 'border-success',
            textClass: 'text-success',
            Icon: Check,
            labelKey: t('Connected'),
        },
        warning: {
            borderClass: 'border-warning',
            textClass: 'text-warning',
            Icon: AlertCircle,
            labelKey: t('Connection issue'),
        },
        disconnected: {
            borderClass: 'border-destructive',
            textClass: 'text-destructive',
            Icon: LinkIcon,
            labelKey: t('Disconnected'),
        },
    } as const;

    const displayName = PROVIDER_DISPLAY_NAMES[type];
    const providerLogo = PROVIDER_LOGOS[type];
    const Icon = STATUS_CONFIG[status].Icon;

    return (
        <Card>
            <CardHeader className="flex w-full items-center gap-2">
                {providerLogo && (
                    <div className="flex size-9 shrink-0 items-center justify-center">
                        <img
                            src={providerLogo}
                            alt={displayName}
                            className="size-full object-contain"
                        />
                    </div>
                )}
                <p className="heading-05">{displayName}</p>
            </CardHeader>
            {status !== 'disconnected' && (
                <CardContent>
                    <>
                        <div
                            className={cn(
                                'flex w-full items-center justify-center gap-1 rounded-md border px-4 py-2',
                                STATUS_CONFIG[status].borderClass
                            )}
                        >
                            <Icon className={cn('size-5', STATUS_CONFIG[status].textClass)} />
                            <span className={cn('body', STATUS_CONFIG[status].textClass)}>
                                {STATUS_CONFIG[status].labelKey}
                            </span>
                        </div>
                    </>
                </CardContent>
            )}

            <CardFooter>
                {status === 'disconnected' ? (
                    <Button
                        variant="secondary"
                        className="w-full"
                        onClick={onConnect}
                        disabled={isConnecting}
                    >
                        <LinkIcon className="size-4" />
                        {t('Connect')}
                    </Button>
                ) : (
                    <Button variant="ghost" className="w-full" onClick={onEdit}>
                        <Pencil className="size-4" />
                        {t('Edit connection')}
                    </Button>
                )}
            </CardFooter>
        </Card>
    );
}
