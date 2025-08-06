import { IChatMessage } from '@/api/chat/types.ts';
import { cn } from '@/lib/utils.ts';
import { Avatar, AvatarFallback } from '@/components/ui/avatar.tsx';

export function ChatUserMessage({
    classNames,
    message,
}: {
    classNames?: string;
    message: IChatMessage;
}) {
    return (
        <div className={cn('w-fit flex gap-2 p-3 bg-gray-900 rounded-md items-center', classNames)}>
            <Avatar>
                <AvatarFallback>U</AvatarFallback>
            </Avatar>
            <p className="">{message.content}</p>
        </div>
    );
}
