import { useRef, useEffect, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import drLogoDark from '@/assets/DataRobot_black.svg';
import drLogoLight from '@/assets/DataRobot_white.svg';
import { useTheme } from '@/theme/theme-provider';
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
import { Heading } from '@/components/ui/heading';

const Chat = () => {
    const { theme } = useTheme();
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
                <div className="flex size-full flex-col items-center justify-center">
                    <div className="flex">
                        <img
                            src={theme === 'dark' ? drLogoLight : drLogoDark}
                            alt="DataRobot"
                            className="ml-2.5 w-[130px] cursor-pointer py-3.5"
                        />
                    </div>
                    <Heading level={1} className="my-4" data-testid="app-model-name">
                        {selectedLlmModel.name}
                    </Heading>
                    <ChatPromptInput isDisabled={disableChatPrompt} />
                </div>
            </ChatSessionProvider>
        );
    }

    return (
        <ChatSessionProvider value={chatSession}>
            <div
                className="flex min-h-[calc(100vh-4rem)] w-full flex-col items-center"
                data-testid="chat-conversation-view"
            >
                <ScrollArea
                    className="scroll mb-5 w-full flex-1 overflow-auto"
                    scrollViewportRef={containerRef}
                >
                    <div className="w-full justify-self-center px-4">
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
