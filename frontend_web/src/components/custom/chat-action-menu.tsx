import { useCallback, useState } from 'react';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu.tsx';
import { Button } from '@/components/ui/button.tsx';
import { EllipsisVertical, TextCursorInput, Trash } from 'lucide-react';
import { IChat } from '@/api/chat/types.ts';
import { useAppState } from '@/state';
import { useTranslation } from '@/lib/i18n';

export function ChatActionMenu({ chat }: { chat: IChat }) {
    const { t } = useTranslation();
    const [open, setOpen] = useState(false);
    const { setShowRenameChatModalForId, setShowDeleteChatModalForId } = useAppState();

    const handleDeleteChat = useCallback(
        (chatId: string) => {
            setOpen(false);
            setShowDeleteChatModalForId(chatId);
        },
        [setShowDeleteChatModalForId]
    );

    const handleRenameChat = useCallback(
        (chatId: string) => {
            setOpen(false);
            setShowRenameChatModalForId(chatId);
        },
        [setShowRenameChatModalForId]
    );

    return (
        <DropdownMenu open={open} onOpenChange={setOpen}>
            <DropdownMenuTrigger asChild>
                <Button
                    className="cursor-pointer justify-self-end"
                    variant="ghost"
                    size="icon"
                    onClick={() => true}
                >
                    <EllipsisVertical strokeWidth="3" />
                </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => handleRenameChat(chat.uuid)} variant="default">
                    <TextCursorInput />
                    {t('Rename')}
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => handleDeleteChat(chat.uuid)} variant="destructive">
                    <Trash />
                    {t('Delete')}
                </DropdownMenuItem>
            </DropdownMenuContent>
        </DropdownMenu>
    );
}
