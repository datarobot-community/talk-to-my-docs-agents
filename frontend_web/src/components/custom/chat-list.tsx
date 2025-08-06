import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useChats } from '@/api/chat/hooks';
import { SidebarMenuButton, SidebarMenuSub, SidebarMenuSubItem } from '@/components/ui/sidebar';
import { Spinner } from '@/components/ui/spinner.tsx';

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
        <SidebarMenuSub className="mx-2">
            {chats.map(chat => (
                <SidebarMenuSubItem key={chat.uuid} className="mb-2">
                    <SidebarMenuButton
                        asChild
                        isActive={location.pathname === `/chat/${chat.uuid}`}
                    >
                        <Link
                            to={`/chat/${chat.uuid}`}
                            title={chat.name || 'New Chat'}
                            className="truncate"
                            data-testid={`chat-link-${chat.uuid}`}
                        >
                            {chat.name || 'New Chat'}
                        </Link>
                    </SidebarMenuButton>
                </SidebarMenuSubItem>
            ))}
        </SidebarMenuSub>
    );
};
