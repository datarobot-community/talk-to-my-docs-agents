import { http, HttpResponse } from 'msw';
import { DEFAULT_LLM_CATALOG } from '@/api/chat/constants.ts';

export const chatHandlers = [
    http.post('api/v1/chat/completions', () => {
        return HttpResponse.json({
            role: 'assistant',
            content: 'Hello World!',
            chat_id: '456',
            uuid: 'def-456'
        });
    }),
    http.post('api/v1/chat/agent/completions', () => {
        return HttpResponse.json({
            role: 'assistant',
            content: 'Agents Say Hello World!',
            chat_id: '123',
            uuid: 'abc-123'
        });
    }),

    http.get('api/v1/chat/llm/catalog', () => {
        return HttpResponse.json({ data: DEFAULT_LLM_CATALOG });
    }),

    http.get('api/v1/chat', () => {
        return HttpResponse.json([]);
    }),
];
