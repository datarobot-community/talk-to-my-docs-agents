import { defineConfig } from 'eslint/config';
import eslint from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import tseslint from 'typescript-eslint';
import i18next from 'eslint-plugin-i18next';
import prettier from 'eslint-plugin-prettier';
import prettierConfig from 'eslint-config-prettier';
import eslintPluginBetterTailwindcss from 'eslint-plugin-better-tailwindcss';

export default defineConfig(
    eslint.configs.recommended,
    tseslint.configs.recommended,
    i18next.configs['flat/recommended'],
    prettierConfig,
    { ignores: ['dist'] },
    {
        files: ['**/*.{ts,tsx}'],
        languageOptions: {
            ecmaVersion: 2020,
            globals: globals.browser,
        },
        plugins: {
            'react-hooks': reactHooks,
            'react-refresh': reactRefresh,
            prettier: prettier,
        },
        rules: {
            ...reactHooks.configs.recommended.rules,
            'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
            'prettier/prettier': 'error',
            'no-restricted-imports': [
                'error',
                {
                    paths: [
                        {
                            name: 'react-i18next',
                            importNames: ['useTranslation'],
                            message:
                                'Import useTranslation from @/lib/i18n instead of react-i18next directly',
                        },
                        {
                            name: 'i18next',
                            message:
                                'Import i18n from @/lib/i18n instead of i18next directly',
                        },
                    ],
                },
            ],
        },
    },
    {
        files: ['**/*.{jsx,tsx}'],
        plugins: {
            'better-tailwindcss': eslintPluginBetterTailwindcss,
        },
        rules: {
            'better-tailwindcss/enforce-consistent-class-order': ['error', { order: 'official' }],
            'better-tailwindcss/enforce-shorthand-classes': 'error',
            'better-tailwindcss/no-conflicting-classes': 'error',
            'better-tailwindcss/no-duplicate-classes': 'error',
            'better-tailwindcss/no-unnecessary-whitespace': 'error',
            'better-tailwindcss/no-deprecated-classes': 'off',
            'better-tailwindcss/enforce-consistent-variable-syntax': [
                'error',
                { syntax: 'shorthand' },
            ],
            'better-tailwindcss/enforce-consistent-important-position': [
                'error',
                { position: 'recommended' },
            ],
        },
        settings: {
            'better-tailwindcss': {
                entryPoint: 'src/index.css',
            },
        },
    },
    // Allow direct i18n imports in the i18n setup files
    {
        files: ['src/lib/i18n/**/*.{ts,tsx}', 'src/main.tsx'],
        rules: {
            'no-restricted-imports': 'off',
        },
    }
);
