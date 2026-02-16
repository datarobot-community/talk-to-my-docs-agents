import React from 'react';
import { useChats } from '@/api/chat/hooks';
import { getChatNameOrDefaultWithTimestamp } from '@/lib/utils.ts';
import { ScrollArea } from '@/components/ui/scroll-area';
import { ChatActionMenu } from '@/components/custom/chat-action-menu.tsx';
import { TruncatedWithTooltip } from '@/components/custom/truncated-with-tooltip.tsx';
import { Heading } from '@/components/ui/heading';
import { useTranslation } from '@/lib/i18n';

export const SettingsChats: React.FC = () => {
    const { t } = useTranslation();
    const { data: chats = [], isLoading } = useChats();

    if (isLoading) return <div>{t('Loading chats...')}</div>;

    return (
        <div className="p-8">
            <Heading level={2} className="mb-2">
                {t('Chats')}
            </Heading>
            <ScrollArea>
                <ul className="max-h-[calc(100vh-200px)] space-y-2">
                    {chats.map(chat => (
                        <li
                            key={chat.uuid}
                            className="mb-2 flex items-center justify-between rounded-md body p-4 hover:bg-muted"
                        >
                            <div className="flex items-center justify-between">
                                <TruncatedWithTooltip
                                    text={getChatNameOrDefaultWithTimestamp(chat)}
                                    triggerClasses="cursor-default max-w-[400px]"
                                />
                            </div>
                            <ChatActionMenu chat={chat} />
                        </li>
                    ))}
                </ul>
            </ScrollArea>
        </div>
    );
};
