import { useCallback, useState } from 'react';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu.tsx';
import { Button } from '@/components/ui/button.tsx';
import { EllipsisVertical, Trash } from 'lucide-react';
import { FileSchema } from '@/api/knowledge-bases/types.ts';
import { useTranslation } from '@/lib/i18n';

export function FileActionMenu({
    file,
    onDelete,
    ariaLabel: defaultAriaLabel,
}: {
    file: FileSchema;
    onDelete: (file: FileSchema) => void;
    ariaLabel?: string;
}) {
    const { t } = useTranslation();
    const [open, setOpen] = useState(false);
    const ariaLabel = defaultAriaLabel || t('File actions');

    const handleOnDelete = useCallback(
        (file: FileSchema) => {
            setOpen(false);
            onDelete(file);
        },
        [onDelete]
    );

    return (
        <DropdownMenu open={open} onOpenChange={setOpen}>
            <DropdownMenuTrigger asChild>
                <Button
                    className="justify-self-end"
                    variant="ghost"
                    size="icon"
                    onClick={() => true}
                    aria-label={ariaLabel}
                >
                    <EllipsisVertical strokeWidth="4" />
                </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => handleOnDelete(file)} variant="destructive">
                    <Trash />
                    {t('Delete')}
                </DropdownMenuItem>
            </DropdownMenuContent>
        </DropdownMenu>
    );
}
