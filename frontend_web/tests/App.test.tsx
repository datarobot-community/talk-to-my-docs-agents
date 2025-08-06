import { screen, waitForElementToBeRemoved } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { userEvent } from '@testing-library/user-event';
import App from '@/App';
import { renderWithProviders } from './test-utils.tsx';
import { DEFAULT_LLM_CATALOG } from '@/api/chat/constants.ts';
import { AppState } from '@/state/types.ts';
import { PATHS } from '@/constants/paths.ts';

describe('Application', () => {
    it('renders the initial layout', async () => {
        renderWithProviders(<App />, {
            selectedLlmModel: DEFAULT_LLM_CATALOG[0],
            availableLlmModels: DEFAULT_LLM_CATALOG,
            selectedKnowledgeBase: null,
        } as AppState);

        const loader = screen.getByTestId('app-loader');
        expect(loader).toBeInTheDocument();

        await waitForElementToBeRemoved(() => screen.getByTestId('app-loader'));
        const header = screen.getByTestId('app-header');
        expect(header).toBeInTheDocument();

        const sidebar = screen.getByTestId('app-sidebar');
        expect(sidebar).toBeInTheDocument();

        const modelSelectorTrigger = await screen.findByTestId('dropdown-model-selector-trigger');
        expect(modelSelectorTrigger).toBeInTheDocument();
        expect(modelSelectorTrigger).toHaveTextContent('🧠 Intelligent Agent Crew');

        const chatPromptInput = await screen.findByTestId('chat-prompt-input');
        expect(chatPromptInput).toBeInTheDocument();
    });

    it('changes selected model via app state context', async () => {
        renderWithProviders(<App />, {
            selectedLlmModel: DEFAULT_LLM_CATALOG[0],
            availableLlmModels: DEFAULT_LLM_CATALOG,
            selectedKnowledgeBase: null,
        } as AppState);

        const modelName = await screen.findByTestId('app-model-name');
        expect(modelName).toHaveTextContent('🧠 Intelligent Agent Crew');

        const modelSelectorTrigger = screen.getByTestId('dropdown-model-selector-trigger');
        expect(modelSelectorTrigger).toBeInTheDocument();
        expect(modelSelectorTrigger).toHaveTextContent('🧠 Intelligent Agent Crew');

        await userEvent.click(modelSelectorTrigger);

        // const modelSelectorMenuContent = screen.getByTestId('dropdown-model-selector-menu-content');
        const gpt4oItem = await screen.findByTestId(
            'dropdown-model-selector-item-azure-openai-gpt-4-o'
        );
        expect(gpt4oItem).toBeVisible();
        await userEvent.click(gpt4oItem);
        expect(modelSelectorTrigger).toHaveTextContent('Azure OpenAI GPT-4o');

        expect(modelName).toHaveTextContent('Azure OpenAI GPT-4o');
    });

    it('modal dropdown should be hidden for on knowledge bases page', async () => {
        renderWithProviders(
            <App />,
            {
                selectedLlmModel: DEFAULT_LLM_CATALOG[0],
                availableLlmModels: DEFAULT_LLM_CATALOG,
                selectedKnowledgeBase: null,
            } as AppState,
            PATHS.KNOWLEDGE_BASES
        );

        expect(screen.queryByTestId('dropdown-model-selector-trigger')).not.toBeInTheDocument();
    });
});
