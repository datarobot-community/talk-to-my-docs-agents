import { Outlet } from 'react-router-dom';
import { Heading } from '@/components/ui/heading';
import { SettingsSources } from '@/components/custom/settings-sources.tsx';
import { DisplaySettings } from '@/components/custom/display-settings.tsx';
import { useTranslation } from '@/lib/i18n';

export const SettingsLayout = () => {
    const { t } = useTranslation();
    return (
        <div className="align-start flex h-full flex-1 flex-col justify-start gap-10 p-6">
            <Heading level={3}>{t('App Settings')}</Heading>
            <SettingsSources />
            <DisplaySettings />
            <Outlet />
        </div>
    );
};
