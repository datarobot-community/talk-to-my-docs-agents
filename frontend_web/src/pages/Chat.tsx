import { useRef, useEffect, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import drLogo from '@/assets/DataRobot_white.svg';

import { useAppState } from '@/state';
import { ChatPromptInput } from '@/components/custom/chat-prompt-input.tsx';
import { IChatMessage } from '@/api/chat/types.ts';
import { ScrollArea } from '@/components/ui/scroll-area';
import { ChatUserMessage } from '@/components/custom/chat-user-message';
import { ChatResponseMessage } from '@/components/custom/chat-response-message';
import { ChatLoadingScreen } from '@/components/custom/chat-loading-screen';
import { useChatMessages } from '@/api/chat/hooks.ts';
import { useChatStream } from '@/hooks/useChatStream';
import { useChatSession } from '@/hooks';
import { ChatSessionProvider } from '@/state/ChatSessionContext';

const Chat = () => {
    const { selectedLlmModel } = useAppState();
    const { chatId } = useParams<{ chatId: string }>();
    const chatSession = useChatSession(chatId);
    const { isPollingFallbackActive } = useChatStream(chatId);
    const { data: messages = [], isLoading: isMessagesLoading } = useChatMessages({
        chatId,
        shouldRefetch: isPollingFallbackActive ? 5000 : undefined,
    });
    const containerRef = useRef<HTMLDivElement>(null);

    const disableChatPrompt = useMemo(
        () => Boolean(chatSession.isLoading || messages?.[messages.length - 1]?.in_progress),
        [chatSession.isLoading, messages]
    );

    useEffect(() => {
        const timeoutId = setTimeout(() => {
            containerRef.current?.scrollTo({
                top: containerRef.current.scrollHeight, // Scroll to the bottom
                behavior: 'smooth',
            });
        }, 300); // Delay to ensure all messages are rendered

        return () => clearTimeout(timeoutId);
    }, [messages]);

    if (isMessagesLoading) {
        return <ChatLoadingScreen />;
    }

    //If there are no messages or if chatId is not defined, show the initial prompt input
    if (messages.length === 0 || (!chatId && !chatSession.isLoading)) {
        return (
            <ChatSessionProvider value={chatSession}>
                <div className="flex flex-col items-center justify-center w-full h-full">
                    <div className="flex">
                        <img
                            src={drLogo}
                            alt="DataRobot"
                            className="w-[130px] cursor-pointer ml-2.5 py-3.5"
                        />
                    </div>
                    <h1 className="text-4xl my-4" data-testid="app-model-name">
                        {selectedLlmModel.name}
                    </h1>
                    <ChatPromptInput isDisabled={disableChatPrompt} />
                </div>
            </ChatSessionProvider>
        );
    }

    return (
        <ChatSessionProvider value={chatSession}>
            <div
                className="flex flex-col items-center w-full min-h-[calc(100vh-4rem)]"
                data-testid="chat-conversation-view"
            >
                <ScrollArea
                    className="flex-1 w-full overflow-auto mb-5 scroll"
                    scrollViewportRef={containerRef}
                >
                    <div className="justify-self-center px-4 w-full">
                        {messages.map((message: IChatMessage, index: number) =>
                            message.role === 'user' ? (
                                <ChatUserMessage
                                    message={message}
                                    key={`user-msg-${message.uuid || index}`}
                                />
                            ) : (
                                <ChatResponseMessage
                                    message={message}
                                    key={`llm-msg-${message.uuid}`}
                                />
                            )
                        )}
                    </div>
                </ScrollArea>
                <ChatPromptInput
                    isDisabled={disableChatPrompt}
                    classNames="w-full self-end self-center mb-2 py-0 px-4"
                />
            </div>
        </ChatSessionProvider>
    );
};

export default Chat;
