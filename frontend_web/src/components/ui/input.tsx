import * as React from 'react';

import { cn } from '@/lib/utils';

const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<'input'>>(
    ({ className, type, ...props }, ref) => {
        return (
            <input
                type={type}
                className={cn(
                    `
            flex field-sizing-content h-9 w-full rounded-lg border border-border bg-input px-3 py-2 text-base shadow-xs
            transition-[color,box-shadow,border] duration-300 outline-none
            placeholder:text-muted-foreground
            hover:border-muted-foreground
            focus:border-accent
            disabled:cursor-not-allowed disabled:border-border/20
            placeholder:disabled:text-muted-foreground/50
            aria-invalid:border-destructive-foreground
            md:text-sm
          `,
                    className
                )}
                ref={ref}
                {...props}
            />
        );
    }
);
Input.displayName = 'Input';

export { Input };
