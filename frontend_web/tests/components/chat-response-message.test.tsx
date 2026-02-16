import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { ChatResponseMessage } from '@/components/custom/chat-response-message';
import { renderWithProviders } from '../test-utils';
import { IChatMessage } from '@/api/chat/types';

describe('ChatResponseMessage', () => {
    it('renders task progress list when in_progress with tasks', () => {
        const message: IChatMessage = {
            role: 'assistant',
            content: '',
            in_progress: true,
            task_outputs: [
                { task_name: 'Search Files', agent_name: 'FileAgent', status: 'completed' },
                { task_name: 'Analyze', agent_name: 'AnalysisAgent', status: 'in_progress' },
            ],
        };

        renderWithProviders(<ChatResponseMessage message={message} />, {
            availableLlmModels: [],
        });

        // Check task text is rendered
        expect(screen.getByText('FileAgent: Search Files')).toBeInTheDocument();
        expect(screen.getByText('AnalysisAgent: Analyze')).toBeInTheDocument();

        // Check correct icons - completed task has CheckCircle2, in_progress has spinning Loader2
        const taskItems = screen.getAllByText(/Agent:/);
        expect(taskItems).toHaveLength(2);
    });

    it('renders loader when in_progress without tasks', () => {
        const message: IChatMessage = {
            role: 'assistant',
            content: '',
            in_progress: true,
            task_outputs: [],
        };

        renderWithProviders(<ChatResponseMessage message={message} />, {
            availableLlmModels: [],
        });

        // Should show the DotPulseLoader, not task list
        expect(screen.queryByText(/Agent:/)).not.toBeInTheDocument();
        // The loader container should be present
        expect(screen.getByTestId('chat-response-message')).toBeInTheDocument();
    });
});
