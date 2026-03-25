import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@/lib/utils';

const ALERT_VARIANT = {
    destructive: 'destructive',
    info: 'info',
    warning: 'warning',
    success: 'success',
};

const alertVariants = cva(
    `
    relative grid w-full grid-cols-[0_1fr] items-start gap-y-0.5 rounded-lg border bg-input body p-4
    has-[>svg]:grid-cols-[calc(var(--spacing)*5)_1fr] has-[>svg]:gap-x-3
    [&>svg]:size-5
  `,
    {
        variants: {
            variant: {
                [ALERT_VARIANT.info]: `
          border-primary
          [&>svg]:text-primary
        `,
                [ALERT_VARIANT.destructive]: `
          border-[color-mix(in_srgb,var(--destructive)_75%,white)]
          [&>svg]:text-[color-mix(in_srgb,var(--destructive)_75%,white)]
        `,
                [ALERT_VARIANT.warning]: `
          border-warning/75
          [&>svg]:text-warning/75
        `,
                [ALERT_VARIANT.success]: `
          border-success/75
          [&>svg]:text-success/75
        `,
            },
        },
        defaultVariants: {
            variant: ALERT_VARIANT.info,
        },
    }
);

function Alert({
    className,
    variant,
    ...props
}: React.ComponentProps<'div'> & VariantProps<typeof alertVariants>) {
    return (
        <div
            data-slot="alert"
            role="alert"
            className={cn(alertVariants({ variant }), className)}
            {...props}
        />
    );
}

function AlertTitle({ className, ...props }: React.ComponentProps<'div'>) {
    return (
        <div
            data-slot="alert-title"
            className={cn(
                `
          col-start-2 line-clamp-1 min-h-4 body tracking-tight
          [&:not(:last-child)]:mb-1
        `,
                className
            )}
            {...props}
        />
    );
}

function AlertDescription({ className, ...props }: React.ComponentProps<'div'>) {
    return (
        <div
            data-slot="alert-description"
            className={cn(
                `
          col-start-2 grid justify-items-start gap-1 caption-01
          [&_p]:leading-relaxed
        `,
                className
            )}
            {...props}
        />
    );
}

function AlertFooter({ className, ...props }: React.ComponentProps<'div'>) {
    return (
        <div
            data-slot="alert-footer"
            className={cn(
                `
          col-start-2 mt-4 flex min-h-0 items-center gap-4 body
          [&>*:first-child]:pl-0
          [&>a]:no-underline
        `,
                className
            )}
            {...props}
        />
    );
}

export { Alert, AlertTitle, AlertDescription, AlertFooter, ALERT_VARIANT };
