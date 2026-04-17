import React, { useState, useRef, useLayoutEffect, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from '@/components/ui/tooltip';
import type * as TooltipPrimitive from '@radix-ui/react-tooltip';

const MIN_LINE_HEIGHT = 1.2;

type TruncateWithTooltipProps = {
    /** Support only one html elements */
    children: React.ReactElement<React.HTMLAttributes<HTMLElement>>;

    /** Set tooltip placement */
    tooltipPlacement?: TooltipPrimitive.TooltipContentProps['side'];
    /** Set custom tooltip text instead of content text */
    tooltipText?: ReactNode;
    /** The delay duration in milliseconds before showing the tooltip */
    tooltipDelayDuration?: number;
    tooltipTestId?: string;
    /** Extend the styles applied to the container  */
    className?: string;
    /** If true, the tooltip will be disabled */
    isDisabled?: boolean;
    tooltipId?: string;
};

/**
 * The component recognizes whether a text element is overflowed truncate it with CSS and provide full text in the tooltip.
 * - supports custom tooltip text with custom placement.
 * - supports only one element as children inside
 * - need provide any HTML element inside component like <span> or <p>.
 * 🚨 NOTE ➡️: max-width & min-width for a parent element is required for proper work. 🚨
 * */
export const TruncateWithTooltip = ({
    children,
    tooltipPlacement = 'top',
    tooltipText,
    tooltipId,
    tooltipDelayDuration = 100,
    tooltipTestId,
    className,
    isDisabled = false,
}: TruncateWithTooltipProps) => {
    const [isTruncating, setTruncating] = useState<boolean>(false);
    const [needLineHeight, setNeedLineHeight] = useState<boolean>(false);
    const [contentText, setContentText] = useState<ReactNode | null>(null);
    const elementRef = useRef(null);
    // NOTE: This solution has a potential issue with a pixel or two when the text is long enough and will be ellipsed,
    // but the tooltip is not shown. That happens due to pixel rounding of scrollWidth and clientWidth.
    // While getBoundingClientRect could give us a precise width, it will include padding and borders,
    // and scrollWidth will still be rounded. Thus, we might get many false positives and show a tooltip too many times.
    const doesTextFit = (target: Element) =>
        target.scrollWidth <= target.clientWidth && target.scrollHeight <= target.clientHeight;

    const updateOverflow: React.MouseEventHandler<HTMLElement> = ({ target }) => {
        if (tooltipText || isDisabled) {
            return;
        }

        if (!isTruncating && !doesTextFit(target as Element)) {
            setContentText((target as Element).textContent);
            return setTruncating(true);
        }

        if (isTruncating && doesTextFit(target as Element)) {
            setContentText(null);
            return setTruncating(false);
        }
    };

    const updatedChildren = React.cloneElement(children, {
        className: cn(
            'block truncate overflow-hidden break-words break-all',
            needLineHeight && 'leading-normal',
            className
        ),
        onMouseOver: updateOverflow,
        //@ts-expect-error: ref is not needed for rendering
        ref: elementRef,
    });

    useLayoutEffect(() => {
        if (elementRef.current) {
            const { fontSize, lineHeight } = window.getComputedStyle(elementRef.current);
            const diff = parseFloat(lineHeight) / parseFloat(fontSize);
            // if line-height less then normal, scroll height will be more then clientHeight
            if (MIN_LINE_HEIGHT > diff) {
                setNeedLineHeight(true);
            }
        }
    }, []);

    const content = tooltipText ?? contentText;

    if (isDisabled || (!isTruncating && !tooltipText)) {
        return updatedChildren;
    }

    return (
        <TooltipProvider delayDuration={tooltipDelayDuration}>
            <Tooltip>
                <TooltipTrigger asChild>{updatedChildren}</TooltipTrigger>
                <TooltipContent id={tooltipId} data-testid={tooltipTestId} side={tooltipPlacement}>
                    {content}
                </TooltipContent>
            </Tooltip>
        </TooltipProvider>
    );
};
