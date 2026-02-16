'use client';

import * as React from 'react';
import * as ProgressPrimitive from '@radix-ui/react-progress';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@/lib/utils';

const PROGRESS_VARIANT = {
    default: 'default',
    success: 'success',
    warning: 'warning',
    error: 'error',
} as const;

const progressVariants = cva('size-full flex-1 rounded-full transition-all', {
    variants: {
        variant: {
            [PROGRESS_VARIANT.default]: 'bg-accent',
            [PROGRESS_VARIANT.success]: 'bg-success',
            [PROGRESS_VARIANT.warning]: 'bg-warning',
            [PROGRESS_VARIANT.error]: 'bg-destructive',
        },
    },
    defaultVariants: {
        variant: PROGRESS_VARIANT.default,
    },
});

function Progress({
    className,
    value,
    variant = PROGRESS_VARIANT.default,
    ...props
}: React.ComponentProps<typeof ProgressPrimitive.Root> & VariantProps<typeof progressVariants>) {
    return (
        <ProgressPrimitive.Root
            data-slot="progress"
            className={cn('relative h-2 w-full overflow-hidden rounded-full bg-border', className)}
            value={value}
            {...props}
        >
            <ProgressPrimitive.Indicator
                data-slot="progress-indicator"
                className={progressVariants({ variant })}
                style={{ transform: `translateX(-${100 - (value || 0)}%)` }}
            />
        </ProgressPrimitive.Root>
    );
}

export { Progress, progressVariants };
