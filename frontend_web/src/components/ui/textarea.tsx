import * as React from 'react';

import { cn } from '@/lib/utils';

function Textarea({ className, ...props }: React.ComponentProps<'textarea'>) {
    return (
        <textarea
            data-slot="textarea"
            className={cn(
                `
          flex field-sizing-content min-h-16 w-full rounded-lg border border-muted-foreground/40 bg-input px-3 py-2 text-base shadow-xs
          transition-[color,box-shadow,border] duration-300 outline-none
          placeholder:text-muted-foreground
          hover:border-muted-foreground
          focus:border-accent
          disabled:cursor-not-allowed disabled:border-muted-foreground/20
          placeholder:disabled:text-muted-foreground/50
          aria-invalid:border-destructive
          md:text-sm
        `,
                className
            )}
            {...props}
        />
    );
}

export { Textarea };
