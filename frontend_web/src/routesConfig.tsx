import { lazy } from 'react';
import { Navigate, RouteObject } from 'react-router-dom';

import { KnowledgeBases } from './pages/KnowledgeBases';
import { KnowledgeBaseFormPage } from './pages/KnowledgeBaseForm';
import { SettingsLayout } from './pages/SettingsLayout';
import { PATHS } from '@/constants/paths';

// Lazy-loaded pages
const ChatPage = lazy(() => import('./pages/Chat'));
const OAuthCallback = lazy(() => import('./pages/OAuthCallback'));

export const appRoutes: RouteObject[] = [
    { path: PATHS.CHAT, element: <ChatPage /> },
    { path: PATHS.CHAT_PAGE, element: <ChatPage /> },
    { path: PATHS.KNOWLEDGE_BASES, element: <KnowledgeBases /> },
    { path: PATHS.ADD_KNOWLEDGE_BASE, element: <KnowledgeBaseFormPage /> },
    { path: PATHS.EDIT_KNOWLEDGE_BASE, element: <KnowledgeBaseFormPage /> },
    { path: PATHS.MANAGE_KNOWLEDGE_BASE, element: <KnowledgeBaseFormPage /> },
    {
        path: PATHS.SETTINGS.ROOT,
        element: <SettingsLayout />,
        // Preserve children routes for redirects
        children: [
            { path: 'chats', element: <Navigate to={PATHS.SETTINGS.ROOT} replace /> },
            { path: 'sources', element: <Navigate to={PATHS.SETTINGS.ROOT} replace /> },
        ],
    },
    { path: PATHS.OAUTH_CB, element: <OAuthCallback /> },
    { path: '*', element: <Navigate to={PATHS.CHAT} replace /> },
];
