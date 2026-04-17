'use client';

import * as React from 'react';
import { GripVerticalIcon } from 'lucide-react';
import { Group, Panel, Separator } from 'react-resizable-panels';

import { cn } from '@/lib/utils';

function ResizablePanelGroup({ className, ...props }: React.ComponentProps<typeof Group>) {
    return (
        <Group
            data-slot="resizable-panel-group"
            className={cn(`flex size-full aria-[orientation=vertical]:flex-col`, className)}
            {...props}
        />
    );
}

function ResizablePanel({ ...props }: React.ComponentProps<typeof Panel>) {
    return <Panel data-slot="resizable-panel" {...props} />;
}

function ResizableHandle({
    withHandle,
    className,
    ...props
}: React.ComponentProps<typeof Separator> & {
    withHandle?: boolean;
}) {
    return (
        <Separator
            data-slot="resizable-handle"
            className={cn(
                `bg-border hover:bg-accent focus-visible:ring-ring data-[separator=active]:bg-accent data-[separator=active]:ring-sidebar-border relative flex w-px items-center justify-center outline-hidden after:absolute after:inset-y-0 after:left-1/2 after:w-1 after:-translate-x-1/2 aria-[orientation=horizontal]:h-px aria-[orientation=horizontal]:w-full aria-[orientation=horizontal]:*:rotate-90 aria-[orientation=horizontal]:after:left-0 aria-[orientation=horizontal]:after:h-1 aria-[orientation=horizontal]:after:w-full aria-[orientation=horizontal]:after:translate-x-0 aria-[orientation=horizontal]:after:-translate-y-1/2 data-[separator=active]:ring-3`,
                className
            )}
            {...props}
        >
            {withHandle && (
                <div className="bg-border z-10 flex h-4 w-3 items-center rounded-xs border">
                    <GripVerticalIcon className="size-2.5" />
                </div>
            )}
        </Separator>
    );
}

export { ResizablePanelGroup, ResizablePanel, ResizableHandle };
