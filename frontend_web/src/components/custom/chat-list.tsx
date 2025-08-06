import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useChats } from '@/api/chat/hooks';
import { SidebarMenuButton, SidebarMenu, SidebarMenuItem } from '@/components/ui/sidebar';
import { Spinner } from '@/components/ui/spinner.tsx';
import { cn } from '@/lib/utils.ts';

export const ChatList: React.FC = () => {
    const { data: chats = [], isLoading } = useChats();
    const location = useLocation();
    if (isLoading)
        return (
            <div className="flex flex-row gap-1 text-sm items-center pt-2">
                <Spinner size="small" /> Loading chats...
            </div>
        );

    return (
        <SidebarMenu className="mx-0 justify-items-center">
            {chats.map(chat => (
                <SidebarMenuItem
                    key={chat.uuid}
                    className={cn(
                        'flex gap-2 pr-3 py-2 rounded border-l-2 border-transparent overflow-hidden transition-colors cursor-pointer hover:bg-card',
                        {
                            'rounded-l-none bg-card border-l-2 border-white':
                                location.pathname === `/chat/${chat.uuid}`,
                        }
                    )}
                >
                    <SidebarMenuButton
                        asChild
                        isActive={location.pathname === `/chat/${chat.uuid}`}
                    >
                        <Link
                            to={`/chat/${chat.uuid}`}
                            title={chat.name || 'New Chat'}
                            className="truncate ml-2"
                            data-testid={`chat-link-${chat.uuid}`}
                        >
                            {chat.name || 'New Chat'}
                        </Link>
                    </SidebarMenuButton>
                </SidebarMenuItem>
            ))}
        </SidebarMenu>
    );
};
