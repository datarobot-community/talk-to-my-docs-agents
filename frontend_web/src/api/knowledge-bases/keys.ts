export const knowledgeBasesKeys = {
    all: ['allKnowledgeBases'],
    byId: (id: string) => ['allKnowledgeBases', id],
    files: (knowledgeBaseUuid: string) => ['allKnowledgeBases', knowledgeBaseUuid, 'files'],
    allFiles: ['allFiles'],
};
