import { useTranslation } from '@/lib/i18n';

export const SettingsPlaceholder = ({ title }: { title: string }) => {
    const { t } = useTranslation();
    return (
        <div className="p-8">
            <h2 className="mb-2 text-xl font-semibold">{title}</h2>
            <p className="text-muted-foreground">{t('This section is not implemented yet.')}</p>
        </div>
    );
};
