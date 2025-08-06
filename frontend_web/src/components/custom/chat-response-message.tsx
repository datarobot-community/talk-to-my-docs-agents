import { IChatMessage } from '@/api/chat/types.ts';
import { cn, unwrapMarkdownCodeBlock } from '@/lib/utils.ts';
import { Avatar, AvatarImage } from '@/components/ui/avatar.tsx';
import drIcon from '@/assets/DataRobotLogo_black.svg';
import { useAppState } from '@/state';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { DotPulseLoader } from '@/components/custom/dot-pulse-loader';
import { MarkdownHooks } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeMermaid from 'rehype-mermaid';

export function ChatResponseMessage({
    classNames,
    message,
    isPending,
}: {
    classNames?: string;
    message?: IChatMessage;
    isPending?: boolean;
}) {
    const { availableLlmModels } = useAppState();
    const messageLlmModel =
        message && availableLlmModels?.find(({ model }) => model === message.model);
    const tabTriggerClasses =
        'w-fit border-0 rounded-none text-white dark:text-white hover:cursor-pointer data-[state=active]:border-b-2 data-[state=active]:!border-b-violet-900 data-[state=active]:!bg-transparent flex-0';
    return (
        <div className="my-3 p-3" data-testid="chat-response-message">
            <div className={cn('w-2xl flex gap-2 items-center', classNames)}>
                <Avatar>
                    <AvatarImage src={drIcon} alt="LLM" />
                </Avatar>
                <p className="">{messageLlmModel?.name}</p>
            </div>
            <div className="w-full">
                {isPending && !message ? (
                    <div className="mt-2 bg-gray-900 p-3 w-fit rounded-md">
                        <DotPulseLoader />
                    </div>
                ) : (
                    <Tabs defaultValue="chat" className="w-full mt-2">
                        <TabsList className="w-full bg-background border-b-3 border-b-accent rounded-none p-0 m-0 justify-start">
                            <TabsTrigger value="chat" className={tabTriggerClasses}>
                                Chat
                            </TabsTrigger>
                            <TabsTrigger value="sources" className={tabTriggerClasses}>
                                Sources
                            </TabsTrigger>
                        </TabsList>
                        <TabsContent value="chat">
                            <div className="p-2 w-fit">
                                <MarkdownHooks
                                    remarkPlugins={[remarkGfm]}
                                    rehypePlugins={[
                                        [
                                            rehypeMermaid,
                                            {
                                                dark: true,
                                                mermaidConfig: {
                                                    theme: 'dark',
                                                },
                                            },
                                        ],
                                    ]}
                                    fallback={<div>Processing markdown...</div>}
                                >
                                    {message
                                        ? unwrapMarkdownCodeBlock(message.content)
                                        : 'Message not available'}
                                </MarkdownHooks>
                            </div>
                        </TabsContent>
                        <TabsContent value="sources">
                            <div className="p-2 w-fit">
                                <p>To be implemented...</p>
                            </div>
                        </TabsContent>
                    </Tabs>
                )}
            </div>
        </div>
    );
}
