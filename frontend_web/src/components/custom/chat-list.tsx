import React, { useMemo } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useChats } from '@/api/chat/hooks';
import { SidebarMenuButton, SidebarMenu, SidebarMenuItem } from '@/components/ui/sidebar';
import { Spinner } from '@/components/ui/spinner.tsx';
import { getChatNameOrDefaultWithTimestamp } from '@/lib/utils.ts';
import { ChatActionMenu } from '@/components/custom/chat-action-menu.tsx';
import { TruncateWithTooltip } from '@/components/ui/truncate-with-tooltip';
import { useTranslation } from '@/lib/i18n';

export const ChatList: React.FC = () => {
    const { t } = useTranslation();
    const { data: chats = [], isLoading } = useChats();
    const sortLatestUpdated = useMemo(() => {
        return [...chats].sort(
            (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
        );
    }, [chats]);

    const location = useLocation();
    if (isLoading) {
        return (
            <div className="body flex flex-row items-center gap-1 pt-2">
                <Spinner className="size-6" /> {t('Loading chats...')}
            </div>
        );
    }

    return (
        <SidebarMenu className="mx-0 justify-items-center">
            {sortLatestUpdated.map(chat => (
                <SidebarMenuItem key={chat.uuid}>
                    <SidebarMenuButton
                        asChild
                        isActive={location.pathname === `/chat/${chat.uuid}`}
                    >
                        {/*Need this div as SidebarMenuButton does not allow fragments*/}
                        <div className="p-0">
                            <Link
                                to={`/chat/${chat.uuid}`}
                                aria-label={getChatNameOrDefaultWithTimestamp(chat)}
                                className="ml-2 max-w-[180px] grow"
                                data-testid={`chat-link-${chat.uuid}`}
                            >
                                <TruncateWithTooltip>
                                    <span>{getChatNameOrDefaultWithTimestamp(chat)}</span>
                                </TruncateWithTooltip>
                            </Link>
                            <ChatActionMenu chat={chat} />
                        </div>
                    </SidebarMenuButton>
                </SidebarMenuItem>
            ))}
        </SidebarMenu>
    );
};
