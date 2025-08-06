import { DEFAULT_LLM_CATALOG } from '@/api/chat/constants';

export const ACTION_TYPES = {
    SET_SELECTED_LLM_MODEL: 'SET_SELECTED_LLM_MODEL',
    SET_AVAILABLE_LLM_MODELS: 'SET_AVAILABLE_LLM_MODELS',
    SET_SELECTED_KNOWLEDGE_BASE: 'SET_SELECTED_KNOWLEDGE_BASE',
} as const;

export const STORAGE_KEYS = {
    SELECTED_LLM_MODEL: 'SELECTED_LLM_MODEL',
    SELECTED_KNOWLEDGE_BASE: 'SELECTED_KNOWLEDGE_BASE',
} as const;

export const DEFAULT_VALUES = {
    selectedLlmModel: DEFAULT_LLM_CATALOG[0],
    selectedKnowledgeBase: null,
    availableLlmModels: null,
};

export const DATA_VISIBILITY = {
    DATAROBOT: 'datarobot',
    PRIVATE: 'private',
};
