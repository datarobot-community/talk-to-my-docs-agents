import { IChatMessage } from '@/api/chat/types.ts';
import { cn } from '@/lib/utils.ts';
import { MessageCircleMore } from 'lucide-react';

const UserAvatar = () => (
    <div className="inline-flex size-7.5 flex-col items-center justify-center gap-2.5 overflow-hidden rounded-[100px] bg-[#7c97f8] p-2.5">
        <div className="text-primary-foreground">
            <MessageCircleMore size={22} />
        </div>
    </div>
);

export function ChatUserMessage({
    classNames,
    message,
}: {
    classNames?: string;
    message: IChatMessage;
}) {
    return (
        <div className={cn('bg-card flex w-fit items-center gap-2 rounded-md p-3', classNames)}>
            <UserAvatar />
            <p className="">{message.content}</p>
        </div>
    );
}
