import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils.ts';

export function TruncatedWithTooltip({
    text,
    triggerClasses = 'max-w-xs',
}: {
    text: string;
    triggerClasses: string;
}) {
    return (
        <TooltipProvider>
            <Tooltip>
                <TooltipTrigger asChild>
                    <p className={cn('truncate', triggerClasses)}>{text}</p>
                </TooltipTrigger>
                <TooltipContent className="max-w-xs wrap-break-word whitespace-normal">
                    <p>{text}</p>
                </TooltipContent>
            </Tooltip>
        </TooltipProvider>
    );
}
