import { lazy } from 'react';
import { Navigate } from 'react-router-dom';

import { KnowledgeBases } from './pages/KnowledgeBases';
import { NewKnowledgeBase } from './pages/NewKnowledgeBase';
import { SettingsLayout } from './pages/SettingsLayout';
import { SettingsSources } from './pages/SettingsSources';
import { SettingsChats } from './pages/SettingsChats';
import { SettingsPlaceholder } from './pages/SettingsPlaceholder';
import { PATHS } from '@/constants/paths';

// Lazy-loaded pages
const ChatPage = lazy(() => import('./pages/Chat'));
const OAuthCallback = lazy(() => import('./pages/OAuthCallback'));

export const appRoutes = [
    { path: PATHS.CHAT, element: <ChatPage /> },
    { path: PATHS.CHAT_PAGE, element: <ChatPage /> },
    { path: PATHS.KNOWLEDGE_BASES, element: <KnowledgeBases /> },
    { path: PATHS.ADD_KNOWLEDGE_BASE, element: <NewKnowledgeBase /> },
    { path: PATHS.EDIT_KNOWLEDGE_BASE, element: <NewKnowledgeBase /> },
    { path: PATHS.MANAGE_KNOWLEDGE_BASE, element: <NewKnowledgeBase /> },
    {
        path: PATHS.SETTINGS.ROOT,
        element: <SettingsLayout />,
        children: [
            { index: true, element: <Navigate to="sources" replace /> },
            { path: 'general', element: <SettingsPlaceholder title="General" /> },
            { path: 'chats', element: <SettingsChats /> },
            { path: 'models', element: <SettingsPlaceholder title="Models" /> },
            { path: 'rag', element: <SettingsPlaceholder title="RAG settings" /> },
            { path: 'sources', element: <SettingsSources /> },
        ],
    },
    { path: PATHS.OAUTH_CB, element: <OAuthCallback /> },
    { path: '*', element: <Navigate to={PATHS.CHAT} replace /> },
];
