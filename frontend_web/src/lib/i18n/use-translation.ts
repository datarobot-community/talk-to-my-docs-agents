import { useCallback } from 'react';

import i18n from 'i18next';
import type { TOptions } from 'i18next';
import { initReactI18next, useTranslation as useI18nTranslation } from 'react-i18next';

// Extended options type that adds 'plural' as an alias for 'defaultValue_other'
type ExtendedTOptions = TOptions & {
    plural?: string;
};

// Import translation files
import esTranslations from './locales/es_419.json';
import frTranslations from './locales/fr.json';
import jaTranslations from './locales/ja.json';
import koTranslations from './locales/ko.json';
import ptTranslations from './locales/pt_BR.json';

export const languages = [
    { id: 'en', name: 'English' },
    { id: 'es', name: 'Español' },
    { id: 'fr', name: 'Français' },
    { id: 'ja', name: '日本語' },
    { id: 'ko', name: '한국어' },
    { id: 'pt', name: 'Português' },
];

const updateResources = (data: Record<string, string>) => {
    return Object.keys(data).reduce(
        (acc, key) => {
            acc[key] = data[key] || key;
            return acc;
        },
        {} as Record<string, string>
    );
};

const resources = {
    es: {
        translation: updateResources(esTranslations),
    },
    fr: {
        translation: updateResources(frTranslations),
    },
    ja: {
        translation: updateResources(jaTranslations),
    },
    ko: {
        translation: updateResources(koTranslations),
    },
    pt: {
        translation: updateResources(ptTranslations),
    },
};

const languageKey = 'app_language';

export const getSavedLanguage = () => {
    if (typeof window !== 'undefined') {
        return localStorage.getItem(languageKey);
    }
    return null;
};

export const saveLanguage = (language: string) => {
    if (typeof window !== 'undefined') {
        localStorage.setItem(languageKey, language);
    }
};

i18n.use(initReactI18next).init({
    resources,
    lng: getSavedLanguage() || 'en',
    fallbackLng: 'en',
    interpolation: {
        escapeValue: false,
    },

    react: {
        useSuspense: false,
    },
});

export const useTranslation = () => {
    const { t: originalT, i18n: i18nInstance } = useI18nTranslation();

    type OriginalTFunction = typeof originalT;

    /**
     * Wrapper around t
     * Adds support for 'plural' as an alias for 'defaultValue_other'
     */
    const t: OriginalTFunction = useCallback(
        (...args: Parameters<OriginalTFunction>) => {
            const [key, optionsOrDefaultValue, maybeOptions] = args;

            // t(key, defaultValue, options)
            if (typeof optionsOrDefaultValue === 'string') {
                const options = (maybeOptions as ExtendedTOptions) ?? {};
                const { plural, ...restOptions } = options;
                return originalT(key as string, optionsOrDefaultValue, {
                    ...restOptions,
                    defaultValue_other: restOptions.defaultValue_other ?? plural,
                });
            }

            // t(key, options) or t(key)
            const options = (optionsOrDefaultValue as ExtendedTOptions) ?? {};
            const { plural, ...restOptions } = options;

            return originalT(key as string, {
                ...restOptions,
                defaultValue_other: restOptions.defaultValue_other ?? plural,
            });
        },
        [originalT]
    ) as OriginalTFunction;

    return {
        t,
        i18n: i18nInstance,
        changeLanguage: i18nInstance.changeLanguage,
        currentLanguage: i18nInstance.language,
    };
};

export default i18n;
