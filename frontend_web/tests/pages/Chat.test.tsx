import { screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import Chat from '@/pages/Chat';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../test-utils.tsx';
import apiClient from '@/api/apiClient.ts';
import { Routes, Route } from 'react-router-dom';
import { PATHS } from '@/constants/paths.ts';

describe('Page: Chat', () => {
    it('renders the initial chat input', async () => {
        renderWithProviders(<Chat />);

        const modelText = await screen.findByText('🧠 Intelligent Agent Crew');
        const textArea = await screen.findByTestId('chat-prompt-input-textarea');
        const submitBtn = await screen.findByTestId('chat-prompt-input-submit');
        expect(modelText).toBeInTheDocument();
        expect(textArea).toBeInTheDocument();
        expect(submitBtn).toBeInTheDocument();
    });

    it('submits prompts to the chat completion endpoint', async () => {
        const postSpy = vi.spyOn(apiClient, 'post');
        renderWithProviders(<Chat />);
        const textArea = await screen.findByTestId('chat-prompt-input-textarea');
        const submitBtn = await screen.findByTestId('chat-prompt-input-submit');

        await userEvent.type(textArea, 'Hello');
        await userEvent.click(submitBtn);

        expect(postSpy).toHaveBeenCalledWith(
            '/v1/chat/agent/completions',
            {
                message: 'Hello',
                model: 'ttmdocs-agents',
                chat_id: undefined,
                knowledge_base: undefined,
            },
            { signal: undefined }
        );
    });

    it('renders the chat conversation after a message has been sent', async () => {
        renderWithProviders(
            <Routes>
                <Route path={PATHS.CHAT} element={<Chat />} />
                <Route path={PATHS.CHAT_PAGE} element={<Chat />} />
            </Routes>,
            undefined,
            PATHS.CHAT
        );
        const textArea = await screen.findByTestId('chat-prompt-input-textarea');
        const submitBtn = await screen.findByTestId('chat-prompt-input-submit');
        await userEvent.type(textArea, 'Hello');
        await userEvent.click(submitBtn);
        const conversationView = await screen.findByTestId('chat-conversation-view');
        expect(conversationView).toBeInTheDocument();

        const responseMessage = await screen.findByTestId('chat-response-message');
        expect(responseMessage).toHaveTextContent('Agents Say Hello World!');
    });
});
