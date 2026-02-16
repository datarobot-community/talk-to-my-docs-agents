import { KnowledgeBaseSchema } from '@/api/knowledge-bases/types';

export interface ITaskOutput {
    task_name: string;
    agent_name: string;
    status: 'in_progress' | 'completed';
}

export interface IChatMessage {
    role: 'user' | 'assistant';
    content: string;
    chat_id?: string;
    components?: string;
    created_at?: string;
    error?: string;
    in_progress?: boolean;
    model?: string;
    uuid?: string;
    task_outputs?: ITaskOutput[];
}

export interface IUserMessage {
    message: string;
    context?: {
        pages?: Record<string, string>;
        fileIds?: string[];
    };
    knowledgeBase?: KnowledgeBaseSchema;
    knowledgeBaseId?: string;
    type?: 'suggestion' | 'message';
}

export interface IPostMessageContext {
    previousMessages: IChatMessage[];
    messagesKey: string[];
    previousChats?: IChat[];
}

export interface IChat {
    uuid: string;
    name: string;
    model: string;
    created_at: string; // ISO date for chat creation time
    updated_at: string; // ISO date for chat creation time
}

export interface IPostMessageParams {
    message: string;
    model: string;
    chatId?: string;
    knowledgeBase?: KnowledgeBaseSchema;
    knowledgeBaseId?: string;
    fileIds?: string[];
    type?: 'suggestion' | 'message';
    signal?: AbortSignal;
}
