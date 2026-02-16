import { useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { Send } from 'lucide-react';
import { useGetKnowledgeBase } from '@/api/knowledge-bases/hooks.ts';
import { useChatSessionContext } from '@/state/ChatSessionContext';
import { useTranslation } from '@/lib/i18n';

export function InteractiveSuggestion({ question }: { question: string }) {
    const { t } = useTranslation();
    const {
        selectedKnowledgeBaseId,
        isLoading,
        selectedFiles,
        actions: { handleSubmit },
    } = useChatSessionContext();

    const actionTooltip = isLoading ? t('Wait for agent to finish responding') : t('Send');

    const { data: selectedKnowledgeBase } = useGetKnowledgeBase(
        selectedKnowledgeBaseId ?? undefined
    );

    const isActionShown = useMemo(() => {
        return Boolean(selectedFiles?.length || selectedKnowledgeBase);
    }, [selectedFiles, selectedKnowledgeBase]);

    return (
        <div className="inline-flex h-fit w-full items-center justify-start gap-2 rounded-md border bg-secondary p-2">
            <div className="shrink grow basis-0 body leading-tight text-primary">{question}</div>
            <div className="h-p flex w-9 items-center justify-center p-2">
                <div className="inline-flex size-5 flex-col items-center justify-center gap-2.5">
                    <div className="cursor-pointer body text-center leading-tight">
                        {isActionShown && (
                            <Button
                                variant="ghost"
                                disabled={isLoading}
                                title={actionTooltip}
                                onClick={() => {
                                    handleSubmit(
                                        false,
                                        question,
                                        selectedKnowledgeBase,
                                        selectedFiles
                                    );
                                }}
                            >
                                <Send />
                            </Button>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
