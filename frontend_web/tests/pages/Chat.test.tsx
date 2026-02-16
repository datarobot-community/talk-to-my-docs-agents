import { screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import Chat from '@/pages/Chat';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../test-utils.tsx';
import apiClient from '@/api/apiClient.ts';
import { Routes, Route } from 'react-router-dom';
import { PATHS } from '@/constants/paths.ts';
import { server } from '../__mocks__/node.ts';
import { http, HttpResponse } from 'msw';
import { eventSourceInstances } from '../setupTests.ts';

describe('Page: Chat', () => {
    beforeEach(() => {
        eventSourceInstances.length = 0;
    });

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
            '/v1/chat',
            {
                message: 'Hello',
                model: 'ttmdocs-agents',
                chat_id: undefined,
                knowledge_base: undefined,
                type: 'message',
            },
            { signal: undefined }
        );
    });

    it('renders the chat conversation after a message has been sent', async () => {
        server.use(
            http.get('api/v1/chat', () => {
                return HttpResponse.json({
                    uuid: 'chat-123-abc',
                    name: 'New Chat',
                    model: 'ttmdocs-agents',
                    created_at: new Date('2025-09-08T12:00:00.000Z').toISOString(),
                    updated_at: new Date('2025-09-08T12:00:00.000Z').toISOString(),
                });
            }),
            http.get('api/v1/chat/:chatId/messages', () => {
                return [
                    HttpResponse.json([
                        {
                            role: 'user',
                            content: 'Hello',
                            chat_id: 'chat-123-abc',
                            uuid: 'abc-123',
                            in_progress: false,
                        },
                        {
                            role: 'assistant',
                            content: 'Agents Say Hello World!',
                            chat_id: 'chat-123-abc',
                            uuid: 'def-456',
                            in_progress: false,
                        },
                    ]),
                ];
            })
        );
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

    it('updates message in real-time when SSE event arrives', async () => {
        const chatId = 'chat-sse-test';

        // Mock the messages endpoint to return initial messages with in_progress
        server.use(
            http.get(`api/v1/chat/${chatId}/messages`, () => {
                return HttpResponse.json([
                    {
                        role: 'user',
                        content: 'Hello',
                        chat_id: chatId,
                        uuid: 'user-msg-1',
                        in_progress: false,
                    },
                    {
                        role: 'assistant',
                        content: '',
                        chat_id: chatId,
                        uuid: 'assistant-msg-1',
                        in_progress: true,
                    },
                ]);
            })
        );

        renderWithProviders(
            <Routes>
                <Route path={PATHS.CHAT_PAGE} element={<Chat />} />
            </Routes>,
            undefined,
            PATHS.CHAT_PAGE.replace(':chatId', chatId)
        );

        // Wait for initial render with in_progress message
        await screen.findByTestId('chat-conversation-view');

        // Get the EventSource instance that was created
        const sseInstance = eventSourceInstances[eventSourceInstances.length - 1];
        expect(sseInstance).toBeDefined();
        expect(sseInstance.url).toContain(chatId);

        // Simulate SSE message update - assistant response completes
        sseInstance.simulateMessage({
            type: 'message',
            data: {
                role: 'assistant',
                content: 'Real-time response from SSE!',
                chat_id: chatId,
                uuid: 'assistant-msg-1',
                in_progress: false,
            },
        });

        // Verify the message updates in the UI
        await waitFor(async () => {
            const responseMessage = await screen.findByTestId('chat-response-message');
            expect(responseMessage).toHaveTextContent('Real-time response from SSE!');
        });
    });
});
