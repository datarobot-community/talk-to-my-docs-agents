import { useMutation, useQueryClient, useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { deleteChatById, getAllChats, getMessages, getLlmCatalog, postMessage } from './requests';
import { chatKeys } from './keys';
import { IChatMessage, IPostMessageContext, IUserMessage, IChat } from './types';
import { useAppState } from '@/state';
import { AGENT_MODEL_LLM } from '@/api/chat/constants.ts';

export const usePostMessage = ({ chatId }: { chatId?: string }) => {
    const { selectedLlmModel } = useAppState();
    const queryClient = useQueryClient();
    const navigate = useNavigate();
    return useMutation<IChatMessage, Error, IUserMessage, IPostMessageContext>({
        mutationFn: ({ message, context, knowledgeBase, knowledgeBaseId }) => {
            // Handle file IDs if present
            if (context?.fileIds && context.fileIds.length > 0) {
                return postMessage({
                    message: message,
                    model: selectedLlmModel.model,
                    chatId: chatId || undefined,
                    knowledgeBase: knowledgeBase || undefined,
                    knowledgeBaseId: knowledgeBaseId || undefined,
                    fileIds: context.fileIds,
                });
            }

            // Fallback to legacy pages format for backward compatibility
            const pages = Array.isArray(context?.pages)
                ? context.pages
                : Object.values(context?.pages || []);

            if (pages.length > 0) {
                console.warn('Legacy pages format detected. Consider updating to use fileIds.');
            }

            return postMessage({
                message: message,
                model: selectedLlmModel.model,
                chatId: chatId || undefined,
                knowledgeBase: knowledgeBase || undefined,
                knowledgeBaseId: knowledgeBaseId || undefined,
                fileIds: undefined,
            });
        },
        onMutate: async data => {
            const { message } = data;
            const messagesKey = chatKeys.messages(chatId);

            const previousMessages = queryClient.getQueryData<IChatMessage[]>(messagesKey) || [];

            const newUserMessage: IChatMessage = {
                role: 'user',
                content: message,
                model: selectedLlmModel.model,
            };
            queryClient.setQueryData(messagesKey, [...previousMessages, newUserMessage]);

            return { previousMessages, messagesKey };
        },
        onError: (_error, _variables, context) => {
            // Restore previous messages
            if (context?.previousMessages && context?.messagesKey) {
                queryClient.setQueryData(context.messagesKey, context.previousMessages);
            }
        },
        onSuccess: data => {
            // Set the chat messages data directly in the cache to avoid loading state
            queryClient.setQueryData<IChatMessage[]>(
                chatKeys.messages(data.chat_id),
                (oldData = []) => [...oldData, data]
            );
            navigate(`/chat/${data.chat_id}`);
        },
    });
};

export const useChatMessages = (chatId?: string) => {
    return useQuery<IChatMessage[]>({
        queryKey: chatKeys.messages(chatId),
        queryFn: async ({ signal }) => {
            const data = await getMessages({ chatId: chatId!, signal });
            return data;
        },
        enabled: !!chatId,
    });
};

export const useChats = () => {
    return useQuery<IChat[]>({
        queryKey: chatKeys.chatList(),
        queryFn: async ({ signal }) => {
            return await getAllChats(signal);
        },
    });
};

export const useChatsDelete = () => {
    const queryClient = useQueryClient();
    return useMutation<void, Error, { chatId: string }>({
        mutationFn: ({ chatId }) => deleteChatById({ chatId }),
        onSettled: () => queryClient.invalidateQueries({ queryKey: chatKeys.chatList() }),
    });
};

export const useLlmCatalog = () => {
    return useQuery({
        queryKey: chatKeys.llmCatalog,
        queryFn: () => getLlmCatalog(),
        select: data => {
            return [AGENT_MODEL_LLM, ...data];
        },
    });
};
