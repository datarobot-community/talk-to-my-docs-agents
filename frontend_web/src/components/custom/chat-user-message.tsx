import { IChatMessage } from '@/api/chat/types.ts';
import { cn } from '@/lib/utils.ts';
import { MessageCircleMore } from 'lucide-react';

const UserAvatar = () => (
    <div className="w-7.5 h-7.5 p-2.5 bg-[#7c97f8] rounded-[100px] flex-col justify-center items-center gap-2.5 inline-flex overflow-hidden">
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
        <div className={cn('w-fit flex gap-2 p-3 bg-card rounded-md items-center', classNames)}>
            <UserAvatar />
            <p className="">{message.content}</p>
        </div>
    );
}
