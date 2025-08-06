import { chatHandlers } from './handlers/chat';
import { knowledgeBasesHandlers } from './handlers/knowledge-bases';
import { userHandlers } from './handlers/user';

export const handlers = [...chatHandlers, ...userHandlers, ...knowledgeBasesHandlers];
