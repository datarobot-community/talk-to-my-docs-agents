import { type ComponentProps } from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cn } from '@/lib/utils';

type HeadingLevel = 1 | 2 | 3 | 4 | 5 | 6;
type HeadingTag = 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6';
type HeadingProps = ComponentProps<HeadingTag> & {
    level: HeadingLevel;
    className?: string;
    asChild?: boolean;
};

const CLASS_NAMES = {
    h1: 'heading-01 not-prose',
    h2: 'heading-02 not-prose',
    h3: 'heading-03 not-prose',
    h4: 'heading-04 not-prose',
    h5: 'heading-05 not-prose',
    h6: 'heading-06 not-prose',
};

function Heading({ level, className, asChild = false, ...props }: HeadingProps) {
    const HTag: HeadingTag = `h${level}`;
    const Comp = asChild ? Slot : HTag;

    return <Comp className={cn(CLASS_NAMES[HTag], className)} {...props} />;
}

export { Heading };
export type { HeadingProps };
