import { AppStateData, Action, LLM_MODEL, KnowledgeBaseSchema } from './types';
import { ACTION_TYPES, DEFAULT_VALUES, STORAGE_KEYS } from './constants';
import { getStorageItem, setStorageItem } from './storage';

export const createInitialState = (): AppStateData => {
    return {
        selectedLlmModel: getStorageItem(STORAGE_KEYS.SELECTED_LLM_MODEL)
            ? JSON.parse(getStorageItem(STORAGE_KEYS.SELECTED_LLM_MODEL)!)
            : DEFAULT_VALUES.selectedLlmModel,
        selectedKnowledgeBase: getStorageItem(STORAGE_KEYS.SELECTED_KNOWLEDGE_BASE)
            ? JSON.parse(getStorageItem(STORAGE_KEYS.SELECTED_KNOWLEDGE_BASE)!)
            : DEFAULT_VALUES.selectedKnowledgeBase,
        availableLlmModels: null,
    };
};

export const reducer = (state: AppStateData, action: Action): AppStateData => {
    switch (action.type) {
        case ACTION_TYPES.SET_SELECTED_LLM_MODEL:
            setStorageItem(STORAGE_KEYS.SELECTED_LLM_MODEL, JSON.stringify(action.payload));
            return {
                ...state,
                selectedLlmModel: action.payload,
            };
        case ACTION_TYPES.SET_AVAILABLE_LLM_MODELS:
            return {
                ...state,
                availableLlmModels: action.payload,
            };
        case ACTION_TYPES.SET_SELECTED_KNOWLEDGE_BASE:
            setStorageItem(STORAGE_KEYS.SELECTED_KNOWLEDGE_BASE, JSON.stringify(action.payload));
            return {
                ...state,
                selectedKnowledgeBase: action.payload,
            };
        default:
            return state;
    }
};

export const actions = {
    setSelectedLlmModel: (model: LLM_MODEL): Action => ({
        type: ACTION_TYPES.SET_SELECTED_LLM_MODEL,
        payload: model,
    }),
    setAvailableLlmModels: (models: LLM_MODEL[]): Action => ({
        type: ACTION_TYPES.SET_AVAILABLE_LLM_MODELS,
        payload: models,
    }),
    setSelectedKnowledgeBase: (base: KnowledgeBaseSchema | null): Action => ({
        type: ACTION_TYPES.SET_SELECTED_KNOWLEDGE_BASE,
        payload: base,
    }),
};
