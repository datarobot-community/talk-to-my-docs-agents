export type ValueOf<T> = T[keyof T];

export interface KnowledgeBaseSchema {
    uuid: string;
    title: string;
    description: string;
    token_count: number;
    path: string;
    created_at: string;
    updated_at: string;
    owner_uuid: string;
    files: Array<{
        uuid: string;
        filename: string;
        source: string;
        added: string;
        owner_uuid: string;
    }>;
}

export interface AppStateData {
    selectedLlmModel: LLM_MODEL;
    selectedKnowledgeBase: KnowledgeBaseSchema | null;
    availableLlmModels: LLM_MODEL[] | null;
}

export interface AppStateActions {
    setSelectedLlmModel: (model: LLM_MODEL) => void;
    setSelectedKnowledgeBase: (knowledgeBase: KnowledgeBaseSchema | null) => void;
    setAvailableLlmModels: (availableLlmModels: LLM_MODEL[]) => void;
}

export type AppState = AppStateData & AppStateActions;

export type Action =
    | { type: 'SET_SELECTED_LLM_MODEL'; payload: LLM_MODEL }
    | { type: 'SET_AVAILABLE_LLM_MODELS'; payload: LLM_MODEL[] }
    | { type: 'SET_SELECTED_KNOWLEDGE_BASE'; payload: KnowledgeBaseSchema | null };

export type LLM_MODEL = {
    name: string;
    model: string;
    llmId: string;
    isActive: boolean;
    isDeprecated: boolean;
};
