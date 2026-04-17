import { useState, useEffect } from 'react';
import { Heading } from '@/components/ui/heading';
import { languages, saveLanguage, useTranslation } from '@/lib/i18n';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Monitor, Moon, Sun } from 'lucide-react';
import { useUpdateUserMetadata } from '@/api/auth/hooks';
import { useTheme } from '@/theme/theme-provider';
import { Field, FieldLabel } from '@/components/ui/field';

type ThemeValue = 'light' | 'dark' | 'system';

export const DisplaySettings = () => {
    const { userTheme } = useTheme();
    const { t, changeLanguage, currentLanguage } = useTranslation();
    const { mutate: updateUserMetadata, isPending: isUpdatingUserMetadata } =
        useUpdateUserMetadata();
    const [themeState, setThemeState] = useState<ThemeValue>(userTheme ?? 'system');

    useEffect(() => {
        setThemeState((userTheme ?? 'system') as ThemeValue);
    }, [userTheme]);

    const updateLanguage = (value: string) => {
        saveLanguage(value);
        changeLanguage(value);
        updateUserMetadata({ language: value });
    };

    const onThemeChange = (value: string) => {
        setThemeState(value as ThemeValue);
        updateUserMetadata({ theme: value });
    };

    return (
        <div className="flex flex-0 flex-col gap-4">
            <div className="border-border border-b py-2">
                <Heading level={4}>{t('Display')}</Heading>
            </div>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-1 lg:grid-cols-3">
                <Field>
                    <FieldLabel>{t('Language')}</FieldLabel>
                    <Select
                        value={currentLanguage}
                        onValueChange={updateLanguage}
                        disabled={isUpdatingUserMetadata}
                    >
                        <SelectTrigger>
                            <SelectValue placeholder={t('Select language')} />
                        </SelectTrigger>
                        <SelectContent position="popper" side="bottom">
                            {languages.map(language => (
                                <SelectItem key={language.id} value={language.id}>
                                    {language.name}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </Field>
            </div>

            <div>
                <Field>
                    <FieldLabel>{t('Theme')}</FieldLabel>
                    <Tabs value={themeState} onValueChange={onThemeChange}>
                        <TabsList>
                            <TabsTrigger value="light" disabled={isUpdatingUserMetadata}>
                                <Sun className="size-4" />
                                {t('Light')}
                            </TabsTrigger>
                            <TabsTrigger value="dark" disabled={isUpdatingUserMetadata}>
                                <Moon className="size-4" />
                                {t('Dark')}
                            </TabsTrigger>
                            <TabsTrigger value="system" disabled={isUpdatingUserMetadata}>
                                <Monitor className="size-4" />
                                {t('System')}
                            </TabsTrigger>
                        </TabsList>
                    </Tabs>
                </Field>
            </div>
        </div>
    );
};
