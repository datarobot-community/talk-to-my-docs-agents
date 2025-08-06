export const PATHS = {
    CHAT: '/chat',
    CHAT_PAGE: '/chat/:chatId',
    OAUTH_CB: '/oauth/callback',
    KNOWLEDGE_BASES: '/knowledge-bases',
    ADD_KNOWLEDGE_BASE: '/knowledge-bases/new',
    EDIT_KNOWLEDGE_BASE: '/knowledge-bases/edit/:baseUuid',
    MANAGE_KNOWLEDGE_BASE: '/knowledge-bases/manage/:baseUuid',
    SETTINGS: {
        ROOT: '/settings',
        GENERAL: '/settings/general',
        CHATS: '/settings/chats',
        MODELS: '/settings/models',
        RAG: '/settings/rag',
        SOURCES: '/settings/sources',
    },
} as const;
