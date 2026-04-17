import React from 'react';
import { cn } from '@/lib/utils';

function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
    return <div className={cn('bg-muted animate-pulse rounded-lg', className)} {...props} />;
}

export { Skeleton };
