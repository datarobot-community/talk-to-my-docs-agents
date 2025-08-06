import * as React from 'react';
import * as Collapsible from '@radix-ui/react-collapsible';
import { Button } from '@/components/ui/button';
import { ChevronRight, ChevronDown } from 'lucide-react';

type CollapsibleSectionProps = {
    title: React.ReactNode;
    children: React.ReactNode;
    defaultOpen?: boolean;
};

export const CollapsibleSection: React.FC<CollapsibleSectionProps> = ({
    title,
    children,
    defaultOpen = false,
}) => {
    const [open, setOpen] = React.useState(defaultOpen);

    return (
        <Collapsible.Root open={open} onOpenChange={setOpen}>
            <Collapsible.Trigger asChild>
                <Button variant="ghost" className="text-sm font-normal text-gray-400" size="sm">
                    <span>{title}</span>
                    <span>{open ? <ChevronDown /> : <ChevronRight />}</span>
                </Button>
            </Collapsible.Trigger>
            <Collapsible.Content className="pl-4 pt-2">{children}</Collapsible.Content>
        </Collapsible.Root>
    );
};
