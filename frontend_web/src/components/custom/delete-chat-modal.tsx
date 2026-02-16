import { Button } from '@/components/ui/button';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import { useEffect, useMemo, useState } from 'react';
import { useAppState } from '@/state';
import { useChats, useChatsDelete } from '@/api/chat/hooks.ts';
import { getChatNameOrDefaultWithTimestamp } from '@/lib/utils.ts';
import { useTranslation } from '@/lib/i18n';

export const DeleteChatModal = () => {
    const { t } = useTranslation();
    const [name, setName] = useState<string>('');
    const { showDeleteChatModalForId, setShowDeleteChatModalForId } = useAppState();
    const { data: chats = [] } = useChats();
    const { mutate: deleteChat, isPending } = useChatsDelete();

    const chat = useMemo(() => {
        return chats.find(chat => chat.uuid === showDeleteChatModalForId);
    }, [chats, showDeleteChatModalForId]);

    const handleXButton = (open: boolean) => {
        if (!open) {
            setShowDeleteChatModalForId(null);
        }
    };

    useEffect(() => {
        if (chat) {
            // Fix stale name between dialog component render and name at the time of opening the dialog
            setName(getChatNameOrDefaultWithTimestamp(chat));
        }
    }, [chat]);

    return (
        <Dialog defaultOpen={false} open={!!chat} onOpenChange={handleXButton}>
            <DialogContent className="sm:max-w-[500px]">
                <DialogHeader>
                    <DialogTitle>{t('Delete Chat')}</DialogTitle>
                </DialogHeader>
                <DialogDescription>
                    {t('Are you sure you want to delete this chat?')}
                    <span className="mt-2 block font-bold">{name}</span>
                </DialogDescription>
                <DialogFooter>
                    <Button
                        variant="ghost"
                        onClick={() => {
                            setShowDeleteChatModalForId(null);
                        }}
                    >
                        {t('Cancel')}
                    </Button>
                    <Button
                        variant="destructive"
                        onClick={() => {
                            deleteChat(
                                { chatId: chat!.uuid },
                                {
                                    onSuccess: () => {
                                        setShowDeleteChatModalForId(null);
                                    },
                                }
                            );
                        }}
                        disabled={isPending}
                    >
                        {isPending ? t('Deleting...') : t('Delete')}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
};
