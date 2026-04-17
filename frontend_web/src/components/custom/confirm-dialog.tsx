import React from 'react';
import * as DialogPrimitive from '@radix-ui/react-dialog';
import { Sheet, SheetPortal, SheetClose, SheetOverlay, SheetTitle } from '@/components/ui/sheet';
import { Button } from '../ui/button';
import { Spinner } from '@/components/ui/spinner';
import { useTranslation } from '@/lib/i18n';

export const ConfirmDialog: React.FC<{
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onConfirm?: () => void;
    title?: string;
    confirmButtonText: string;
    confirmLoadingText?: string;
    confirmLoading?: boolean;
    children: React.ReactNode;
}> = ({
    open,
    onOpenChange,
    title,
    onConfirm,
    confirmButtonText,
    confirmLoadingText,
    confirmLoading = false,
    children,
}) => {
    const { t } = useTranslation();
    return (
        <Sheet open={open} onOpenChange={onOpenChange}>
            <SheetPortal>
                <SheetOverlay className="fixed inset-0 z-50 bg-black/50" />
                <DialogPrimitive.Content
                    className="bg-background fixed top-1/2 left-1/2 z-50 w-[540px] -translate-1/2 rounded p-6 shadow-lg"
                    aria-describedby={undefined}
                >
                    {title && <SheetTitle className="mb-4 text-lg font-bold">{title}</SheetTitle>}
                    {children}
                    <div className="mt-6 flex justify-end gap-2">
                        <SheetClose asChild>
                            <Button variant="secondary" disabled={confirmLoading}>
                                {t('Close')}
                            </Button>
                        </SheetClose>
                        <Button variant="destructive" onClick={onConfirm} disabled={confirmLoading}>
                            {confirmLoading ? (
                                <span className="flex items-center gap-2">
                                    <Spinner className="size-6 text-current" />
                                    {confirmLoadingText || confirmButtonText}
                                </span>
                            ) : (
                                confirmButtonText
                            )}
                        </Button>
                    </div>
                </DialogPrimitive.Content>
            </SheetPortal>
        </Sheet>
    );
};
