import * as React from 'react';

import { cn } from '@/lib/utils';

function Textarea({ className, ...props }: React.ComponentProps<'textarea'>) {
    return (
        <textarea
            data-slot="textarea"
            className={cn(
                `border-muted-foreground/40 bg-input placeholder:text-muted-foreground hover:border-muted-foreground focus:border-accent disabled:border-muted-foreground/20 placeholder:disabled:text-muted-foreground/50 aria-invalid:border-destructive-foreground flex field-sizing-content min-h-16 w-full rounded-lg border px-3 py-2 text-base shadow-xs transition-[color,box-shadow,border] duration-300 outline-none disabled:cursor-not-allowed md:text-sm`,
                className
            )}
            {...props}
        />
    );
}

export { Textarea };
