import { IChatMessage, ITaskOutput } from '@/api/chat/types.ts';
import { cn, unwrapMarkdownCodeBlock } from '@/lib/utils.ts';
import { Avatar, AvatarImage } from '@/components/ui/avatar.tsx';
import { Alert, AlertTitle } from '@/components/ui/alert';
import { AlertCircleIcon, CheckCircle2, Loader2 } from 'lucide-react';
import drIcon from '@/assets/DataRobotLogo_black.svg';
import { useAppState } from '@/state';
import { MARKDOWN_COMPONENTS } from '@/constants/markdown';
import { DotPulseLoader } from '@/components/custom/dot-pulse-loader';
import { MarkdownHooks } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeMermaid from 'rehype-mermaid';
import { useTranslation } from '@/lib/i18n';

function TaskProgressList({ taskOutputs }: { taskOutputs: ITaskOutput[] }) {
    return (
        <div className="mt-2 flex w-fit flex-col gap-1 rounded-md bg-card p-4">
            {taskOutputs.map((task, idx) => (
                <div key={idx} className="flex items-center gap-2 text-sm">
                    {task.status === 'completed' ? (
                        <CheckCircle2 className="size-4 shrink-0 text-secondary-foreground" />
                    ) : (
                        <Loader2 className="size-4 shrink-0 animate-spin text-secondary-foreground" />
                    )}
                    {/* TODO: i18n - decide translation strategy for agent/task names when implementing internationalization */}
                    <span className="text-secondary-foreground">
                        {task.agent_name}: {task.task_name}
                    </span>
                </div>
            ))}
        </div>
    );
}

export function ChatResponseMessage({
    classNames,
    message,
}: {
    classNames?: string;
    message: IChatMessage;
}) {
    const { t } = useTranslation();
    const { availableLlmModels } = useAppState();
    const messageLlmModel =
        message && availableLlmModels?.find(({ model }) => model === message.model);
    return (
        <div className="my-3 py-3" data-testid="chat-response-message">
            <div className={cn('flex w-2xl items-center gap-2 px-3', classNames)}>
                <Avatar>
                    <AvatarImage src={drIcon} alt="LLM" />
                </Avatar>
                <p className="">{messageLlmModel?.name}</p>
            </div>
            <div className="w-full">
                {message.in_progress ? (
                    message.task_outputs && message.task_outputs.length > 0 ? (
                        <TaskProgressList taskOutputs={message.task_outputs} />
                    ) : (
                        <div className="mt-2 w-fit rounded-md bg-card p-4">
                            <DotPulseLoader />
                        </div>
                    )
                ) : (
                    <div className="w-fit p-2">
                        {message.error ? (
                            <Alert variant="destructive">
                                <AlertCircleIcon />
                                <AlertTitle>{message.error}</AlertTitle>
                            </Alert>
                        ) : (
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
                                fallback={<div>{t('Processing markdown...')}</div>}
                                components={MARKDOWN_COMPONENTS}
                            >
                                {message
                                    ? unwrapMarkdownCodeBlock(message.content)
                                    : t('Message not available')}
                            </MarkdownHooks>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}
