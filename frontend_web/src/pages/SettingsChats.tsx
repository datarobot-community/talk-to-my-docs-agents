import React from 'react';
import { useChats, useChatsDelete } from '@/api/chat/hooks';
import { Button } from '@/components/ui/button';
import {
    DropdownMenu,
    DropdownMenuTrigger,
    DropdownMenuContent,
    DropdownMenuItem,
} from '@/components/ui/dropdown-menu';
import { EllipsisVertical, Trash } from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';

export const SettingsChats: React.FC = () => {
    const { data: chats = [], isLoading } = useChats();
    const { mutate: deleteChat } = useChatsDelete();

    const handleDeleteChat = (chatId: string) => {
        deleteChat({ chatId });
    };

    if (isLoading) return <div>Loading chats...</div>;

    return (
        <div className="p-8">
            <h2 className="text-xl font-semibold mb-2">Chats</h2>
            <ScrollArea className="max-h-[calc(100vh-200px)]">
                <ul className="space-y-2">
                    {chats.map(chat => (
                        <li
                            key={chat.uuid}
                            className="mb-2 flex items-center justify-between p-4 hover:bg-accent/30 rounded-md text-primary text-gray-500"
                        >
                            <div className="flex items-center justify-between truncate max-w-[400px]">
                                {chat.name || 'New Chat'}
                            </div>
                            <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                    <Button
                                        className="justify-self-end cursor-pointer"
                                        variant="ghost"
                                        size="icon"
                                        onClick={() => true}
                                    >
                                        <EllipsisVertical strokeWidth="4" />
                                    </Button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent align="end">
                                    <DropdownMenuItem
                                        onClick={() => handleDeleteChat(chat.uuid)}
                                        className="cursor-pointer"
                                    >
                                        <Trash />
                                        Delete
                                    </DropdownMenuItem>
                                </DropdownMenuContent>
                            </DropdownMenu>
                        </li>
                    ))}
                </ul>
            </ScrollArea>
        </div>
    );
};
