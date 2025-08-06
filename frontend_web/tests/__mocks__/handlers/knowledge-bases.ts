import { http, HttpResponse } from 'msw';

export const knowledgeBasesHandlers = [
    http.get('api/v1/knowledge-bases', () => {
        return HttpResponse.json({ knowledge_bases: [] });
    }),
];
