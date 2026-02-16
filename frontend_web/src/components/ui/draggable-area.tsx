import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { Slot } from '@radix-ui/react-slot';

export type DraggableAreaProps = Omit<
    React.ComponentProps<'div'>,
    'onDragStart' | 'onDrag' | 'onDragEnd'
> & {
    asChild?: boolean;
    /**
     * Unique identifier for this draggable area
     */
    areaId: string;
    onDragStart?: (event: DraggableEvent) => void;
    onDrag: (event: DraggableEvent) => void;
    onDragEnd?: (event: DraggableEvent | string) => void;
    ariaLabel?: string;
    ariaRole?: 'slider' | 'separator' | 'scrollbar';
};

/**
 * A draggable area component with built-in mouse, touch, and pointer support.
 *
 * @example
 * ```tsx
 * <DraggableArea
 *   areaId="resize-handle"
 *   onDrag={(e) => setWidth(e.clientX)}
 *   ariaLabel="Resize sidebar"
 *   ariaRole="separator"
 *   className="w-1 cursor-col-resize"
 * />
 * ```
 */
export function DraggableArea({
    className,
    asChild = false,
    areaId,
    onDragStart,
    onDrag,
    onDragEnd,
    ariaLabel,
    ariaRole = 'separator',
    style,
    ...props
}: DraggableAreaProps) {
    const { onPointerDown, dragHandleProps, isDragging } = useDraggableArea({
        areaId,
        onDragStart,
        onDrag,
        onDragEnd,
        ariaLabel,
        ariaRole,
    });

    const Comp = asChild ? Slot : 'div';

    return (
        <Comp
            className={cn(className)}
            onPointerDown={onPointerDown}
            data-area-id={areaId}
            data-dragging={isDragging || undefined}
            {...dragHandleProps}
            style={{ ...dragHandleProps.style, ...style }}
            {...props}
        />
    );
}

export type DraggableEvent = {
    areaId: string;
    clientX: number;
    clientY: number;
    pageX: number;
    pageY: number;
    screenX: number;
    screenY: number;
    originalEvent: MouseEvent | TouchEvent | PointerEvent;
};

export type DraggableAreaOptions = {
    areaId: string;
    onDragStart?: (event: DraggableEvent) => void;
    onDrag: (event: DraggableEvent) => void;
    onDragEnd?: (event: DraggableEvent | string) => void;
    ariaLabel?: string;
    ariaRole?: 'slider' | 'separator' | 'scrollbar';
};

/** @deprecated Use DraggableAreaOptions instead */
export type DraggableArea = DraggableAreaOptions;

function createDraggableEvent(
    e: MouseEvent | TouchEvent | PointerEvent,
    areaId: string
): DraggableEvent {
    // Handle touch events
    const point =
        'touches' in e ? e.touches[0] || e.changedTouches[0] : (e as MouseEvent | PointerEvent);

    return {
        areaId,
        clientX: point?.clientX ?? 0,
        clientY: point?.clientY ?? 0,
        pageX: point?.pageX ?? 0,
        pageY: point?.pageY ?? 0,
        screenX: point?.screenX ?? 0,
        screenY: point?.screenY ?? 0,
        originalEvent: e,
    };
}

/**
 * Hook for creating draggable areas with mouse and touch support
 *
 * @param options - Configuration options for the draggable area
 * @returns Object containing event handlers and ARIA props for the draggable element
 *
 * @example
 * ```tsx
 * const { onPointerDown, dragHandleProps, isDragging } = useDraggableArea({
 *   areaId: 'resize-handle',
 *   onDrag: (e) => console.log(e.clientX),
 *   ariaLabel: 'Resize panel',
 * });
 *
 * return <div onPointerDown={onPointerDown} {...dragHandleProps} />;
 * ```
 */
export function useDraggableArea({
    areaId,
    onDragStart = () => {},
    onDrag,
    onDragEnd = () => {},
    ariaLabel,
    ariaRole = 'slider',
}: DraggableAreaOptions) {
    if (process.env.NODE_ENV !== 'production' && !areaId) {
        console.warn('useDraggableArea: areaId is required for proper functionality');
    }

    const [isDragging, setIsDragging] = useState(false);

    const onStart = useCallback(
        (
            e: React.PointerEvent<Element> | React.MouseEvent<Element> | React.TouchEvent<Element>
        ) => {
            // only allow left mouse button (button 0) or touch
            if ('button' in e && e.button !== 0) {
                return;
            }

            const draggableEvent = createDraggableEvent(e.nativeEvent, areaId);
            e.preventDefault();
            e.stopPropagation();
            setIsDragging(true);
            onDragStart(draggableEvent);
        },
        [areaId, onDragStart]
    );

    useEffect(() => {
        if (!isDragging) {
            return;
        }

        function onDragHandler(e: MouseEvent | TouchEvent | PointerEvent) {
            const draggableEvent = createDraggableEvent(e, areaId);
            e.preventDefault();
            onDrag(draggableEvent);
        }

        function onDragEndHandler(e: MouseEvent | TouchEvent | PointerEvent) {
            const draggableEvent = createDraggableEvent(e, areaId);
            e.preventDefault();
            removeListeners();
            setIsDragging(false);
            onDragEnd(draggableEvent);
        }

        function onDragBlurHandler() {
            setIsDragging(false);
            onDragEnd(areaId);
            removeListeners();
        }

        const hasPointerEvents = typeof window.PointerEvent !== 'undefined';

        if (hasPointerEvents) {
            window.addEventListener('pointermove', onDragHandler);
            window.addEventListener('pointerup', onDragEndHandler);
            window.addEventListener('pointercancel', onDragEndHandler);
        } else {
            window.addEventListener('mousemove', onDragHandler);
            window.addEventListener('mouseup', onDragEndHandler);
            window.addEventListener('touchmove', onDragHandler, { passive: false });
            window.addEventListener('touchend', onDragEndHandler);
            window.addEventListener('touchcancel', onDragEndHandler);
        }

        window.addEventListener('blur', onDragBlurHandler);

        function removeListeners() {
            if (hasPointerEvents) {
                window.removeEventListener('pointermove', onDragHandler);
                window.removeEventListener('pointerup', onDragEndHandler);
                window.removeEventListener('pointercancel', onDragEndHandler);
            } else {
                window.removeEventListener('mousemove', onDragHandler);
                window.removeEventListener('mouseup', onDragEndHandler);
                window.removeEventListener('touchmove', onDragHandler);
                window.removeEventListener('touchend', onDragEndHandler);
                window.removeEventListener('touchcancel', onDragEndHandler);
            }
            window.removeEventListener('blur', onDragBlurHandler);
        }

        return removeListeners;
    }, [isDragging, onDrag, onDragEnd, areaId]);

    const dragHandleProps = useMemo(
        () => ({
            role: ariaRole,
            tabIndex: 0,
            'aria-label': ariaLabel ?? `Draggable ${areaId}`,
            'aria-grabbed': isDragging,
            style: { touchAction: 'none' } as React.CSSProperties,
        }),
        [ariaRole, ariaLabel, areaId, isDragging]
    );

    return {
        onPointerDown: onStart,
        onMouseDown: onStart,
        onTouchStart: onStart,
        isDragging,
        /** ARIA props to spread on the draggable element for accessibility */
        dragHandleProps,
    };
}
