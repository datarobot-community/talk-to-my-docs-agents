import { useState, useRef, useEffect, useMemo } from 'react';
import { useParams } from 'react-router-dom';

import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import {
    FileChartColumnIncreasing,
    ArrowUpFromLine,
    BookOpenText,
    CloudUpload,
    Send,
    WandSparkles,
    XIcon,
    Plus,
    Info,
    TriangleAlert,
} from 'lucide-react';
import { cn, formatFileSize } from '@/lib/utils.ts';
import {
    DropdownMenu,
    DropdownMenuTrigger,
    DropdownMenuContent,
    DropdownMenuItem,
} from '@/components/ui/dropdown-menu';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import {
    useFileUploadMutation,
    useListKnowledgeBases,
    useGetKnowledgeBase,
} from '@/api/knowledge-bases/hooks';
import { useChatSessionContext } from '@/state/ChatSessionContext';
import { ConnectedSourcesDialog } from '@/components/custom/connected-sources-dialog';
import { ExternalFile, useExternalFileUploadMutation } from '@/api/external-files';
import { useAppState } from '@/state';
import { AGENT_MODEL } from '@/api/chat/constants';
import { useNavigate } from 'react-router-dom';
import { ROUTES } from '@/pages/routes.ts';
import { Card, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useTranslation } from '@/lib/i18n';

export function ChatPromptInput({
    classNames,
    isDisabled,
}: {
    classNames?: string;
    isDisabled: boolean;
}) {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const fileInputRef = useRef<HTMLInputElement>(null);
    const { chatId } = useParams<{ chatId: string }>();
    const { selectedLlmModel } = useAppState();
    const {
        selectedKnowledgeBaseId,
        selectedExternalFileId,
        selectedLocalFileId,
        messageDraft,
        selectedFiles,
        actions: {
            removeSelectedExternalFileId,
            setSelectedKnowledgeBaseId,
            setSelectedExternalFileId,
            removeSelectedLocalFileId,
            setSelectedLocalFileId,
            setMessageDraft,
            handleSubmit,
        },
    } = useChatSessionContext();

    const { data: selectedKnowledgeBase } = useGetKnowledgeBase(
        selectedKnowledgeBaseId ?? undefined
    );
    const { data: bases = [], isFetched: isKnowledgeBasesFetched } = useListKnowledgeBases();
    const [isSelectFileActionMenuOpen, setIsSelectFileActionMenuOpen] = useState(false);
    const [isConnectedSourcesOpen, setIsConnectedSourcesOpen] = useState(false);
    const [isComposing, setIsComposing] = useState(false);
    const [fileUploadName, setFileUploadName] = useState<string | null>(null);

    const { mutate, isPending: isFileUploading } = useFileUploadMutation({
        onSuccess: data => {
            if (data?.[0]?.uuid) {
                setSelectedLocalFileId(data?.[0]?.uuid);
            }
        },
        onError: error => {
            console.error('Error uploading file:', error);
        },
    });

    // Deselect Knowledge Base when it is no longer found
    useEffect(() => {
        if (
            isKnowledgeBasesFetched &&
            selectedKnowledgeBaseId &&
            !bases.some(base => base.uuid === selectedKnowledgeBaseId)
        ) {
            setSelectedKnowledgeBaseId(null);
        }
    }, [selectedKnowledgeBaseId, bases, isKnowledgeBasesFetched, setSelectedKnowledgeBaseId]);

    const { mutate: mutateExternalFile, isPending: isExternalFileUploading } =
        useExternalFileUploadMutation({
            onSuccess: data => {
                setIsConnectedSourcesOpen(false);
                // We currently only support 1 file selection
                if (data?.[0]?.uuid) {
                    setSelectedExternalFileId(data[0].uuid);
                }
            },
            onError: error => {
                console.error('Error uploading external file:', error);
            },
            knowledgeBaseUuid: selectedKnowledgeBaseId ?? undefined,
        });

    const isAgentModel = selectedLlmModel.model === AGENT_MODEL;

    const showSuggestPromptButton = useMemo(() => {
        return Boolean((selectedFiles?.length || selectedKnowledgeBase) && !messageDraft);
    }, [selectedFiles, selectedKnowledgeBase, messageDraft]);

    const handleMenuClick = () => {
        fileInputRef.current?.click();
    };

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const uploadedFile = e.target.files;
        if (uploadedFile && uploadedFile[0]) {
            setFileUploadName(uploadedFile[0]?.name);
            mutate({ files: [uploadedFile[0]] });
        }
        // Reset the input so the same file can be selected again
        e.target.value = '';
    };

    const handleExternalFileSelect = (file: ExternalFile, source: 'google' | 'box') => {
        // Upload the external file using the new API
        setFileUploadName(file?.name);
        mutateExternalFile({ file, source });
    };

    const handleConnectedSourcesClick = () => {
        setIsSelectFileActionMenuOpen(false);
        setIsConnectedSourcesOpen(true);
    };

    const handleKnowledgeBaseSelect = async (baseUuid: string) => {
        const selectedBase = bases.find(base => base.uuid === baseUuid);
        setSelectedKnowledgeBaseId(selectedBase?.uuid || null);
    };

    const handleAddKnowledgeBase = () => {
        // Navigate to the new base page
        navigate(ROUTES.ADD_KNOWLEDGE_BASE);
    };

    const handleEnterPress = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === 'Enter' && !e.shiftKey && !isComposing) {
            e.preventDefault();
            handleSubmit(false, messageDraft, selectedKnowledgeBase, selectedFiles);
        }
    };

    function onRemove(fileId: string) {
        if (!selectedFiles) return;
        if (selectedLocalFileId.includes(fileId)) {
            removeSelectedLocalFileId(fileId);
        }
        if (selectedExternalFileId.includes(fileId)) {
            removeSelectedExternalFileId(fileId);
        }
    }

    return (
        <>
            <div
                className={cn(
                    isDisabled ? 'cursor-wait opacity-70' : '',
                    'transition-all',
                    'w-2xl justify-items-center p-5',
                    classNames
                )}
                data-testid="chat-prompt-input"
            >
                <Textarea
                    disabled={isDisabled}
                    onChange={e => setMessageDraft(e.target.value)}
                    placeholder={t('Ask anything...')}
                    value={messageDraft}
                    className="resize-none rounded-none"
                    onKeyDown={handleEnterPress}
                    onCompositionStart={() => setIsComposing(true)}
                    onCompositionEnd={() => setIsComposing(false)}
                    data-testid="chat-prompt-input-textarea"
                />
                <div className="w-full border border-t-0 p-1">
                    <div className="flex h-12 items-center justify-between">
                        <div className="flex items-center gap-1">
                            <DropdownMenu
                                open={isSelectFileActionMenuOpen}
                                onOpenChange={setIsSelectFileActionMenuOpen}
                            >
                                <DropdownMenuTrigger asChild>
                                    <Button
                                        className="cursor-pointer justify-self-end"
                                        variant="ghost"
                                        size="icon"
                                        onClick={() => true}
                                        disabled={isDisabled}
                                    >
                                        <Plus strokeWidth="4" />
                                    </Button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent align="end">
                                    <DropdownMenuItem
                                        onClick={handleMenuClick}
                                        className="cursor-pointer"
                                    >
                                        <ArrowUpFromLine />
                                        {t('Upload from computer')}
                                    </DropdownMenuItem>
                                    <DropdownMenuItem
                                        onClick={handleConnectedSourcesClick}
                                        className="cursor-pointer"
                                    >
                                        <CloudUpload />
                                        {t('Upload from connected source')}
                                    </DropdownMenuItem>
                                    {/* Knowledge base selection for all models */}
                                    {bases.length > 0 || selectedKnowledgeBaseId ? (
                                        [
                                            ...bases.map(base => (
                                                <DropdownMenuItem
                                                    key={base.uuid}
                                                    onClick={() =>
                                                        handleKnowledgeBaseSelect(base.uuid)
                                                    }
                                                    className={cn(
                                                        'cursor-pointer',
                                                        selectedKnowledgeBaseId === base.uuid &&
                                                            'bg-primary/10 font-semibold text-primary'
                                                    )}
                                                >
                                                    <BookOpenText
                                                        className={cn(
                                                            selectedKnowledgeBaseId === base.uuid &&
                                                                'text-primary'
                                                        )}
                                                    />
                                                    <div className="ml-2 flex flex-col">
                                                        <span
                                                            className={cn(
                                                                'font-medium',
                                                                selectedKnowledgeBaseId ===
                                                                    base.uuid &&
                                                                    'font-semibold text-primary'
                                                            )}
                                                        >
                                                            {base.title}
                                                        </span>

                                                        <span className="truncate caption-01">
                                                            {t(
                                                                '{{files}} file • {{tokens}} tokens',
                                                                {
                                                                    files: base.files.length,
                                                                    tokens: base.token_count.toLocaleString(),
                                                                    count: base.files.length,
                                                                    plural: '{{files}} files • {{tokens}} tokens',
                                                                }
                                                            )}
                                                        </span>
                                                        {!isAgentModel && (
                                                            <span className="caption-01 text-warning">
                                                                <TriangleAlert className="mr-1 inline-block size-4" />
                                                                {t('High token usage possible')}
                                                            </span>
                                                        )}
                                                    </div>
                                                </DropdownMenuItem>
                                            )),
                                        ]
                                    ) : (
                                        <DropdownMenuItem
                                            onClick={handleAddKnowledgeBase}
                                            className="cursor-pointer"
                                        >
                                            <BookOpenText />
                                            {t('Add knowledge base')}
                                        </DropdownMenuItem>
                                    )}
                                </DropdownMenuContent>
                            </DropdownMenu>
                            <p className="flex items-center gap-2 body-secondary">
                                <Info className="size-5" />
                                {t('Upload a file or select a knowledge base')}
                            </p>
                        </div>
                        <Input
                            ref={fileInputRef}
                            type="file"
                            className="hidden"
                            accept=".txt,.pdf,.docx,.md,.pptx,.csv"
                            onChange={handleFileChange}
                        />
                        <TooltipProvider>
                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <Button
                                        className={cn(
                                            'cursor-pointer justify-self-end',
                                            showSuggestPromptButton &&
                                                !chatId &&
                                                'animate-(--animation-blink-border-and-shadow)'
                                        )}
                                        variant="ghost"
                                        size="icon"
                                        onClick={() =>
                                            handleSubmit(
                                                showSuggestPromptButton,
                                                messageDraft,
                                                selectedKnowledgeBase,
                                                selectedFiles
                                            )
                                        }
                                        data-testid="chat-prompt-input-submit"
                                        disabled={isDisabled}
                                    >
                                        {showSuggestPromptButton ? <WandSparkles /> : <Send />}
                                    </Button>
                                </TooltipTrigger>
                                <TooltipContent
                                    side="left"
                                    className="wrap-break-word whitespace-normal"
                                >
                                    <p>
                                        {showSuggestPromptButton
                                            ? t(
                                                  'Ask DataRobot to suggest questions about your documents.'
                                              )
                                            : t('Submit prompt')}
                                    </p>
                                </TooltipContent>
                            </Tooltip>
                        </TooltipProvider>
                    </div>
                    {selectedKnowledgeBase && (
                        <Card className="mt-2 w-1/2 gap-2 p-2">
                            <div className="spacebetween flex items-center">
                                <CardTitle
                                    size="medium"
                                    className="truncate"
                                    title={selectedKnowledgeBase.title}
                                >
                                    {selectedKnowledgeBase.title}
                                </CardTitle>
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    className="ml-auto"
                                    onClick={() => setSelectedKnowledgeBaseId(null)}
                                >
                                    <XIcon />
                                </Button>
                            </div>
                            <div>
                                <div className="mb-2 flex items-center gap-2 body-secondary">
                                    <Badge variant="info">{t('Knowledge base')}</Badge>
                                    <div className="caption-01">
                                        {t('{{files}} file • {{tokens}} tokens', {
                                            files: selectedKnowledgeBase.files.length,
                                            tokens: selectedKnowledgeBase.token_count.toLocaleString(),
                                            count: selectedKnowledgeBase.files.length,
                                            plural: '{{files}} files • {{tokens}} tokens',
                                        })}
                                    </div>
                                </div>
                                {!isAgentModel && (
                                    <div className="caption-01 font-medium text-warning">
                                        <TriangleAlert className="mr-1 inline-block size-4" />
                                        {t('High token usage possible')}
                                    </div>
                                )}
                            </div>
                        </Card>
                    )}
                    {(isFileUploading || isExternalFileUploading) && (
                        <Skeleton className="my-3 h-10 w-full">
                            <div className="group flex w-full items-center gap-4 pt-2">
                                <div className="flex w-8 items-center justify-center">
                                    <FileChartColumnIncreasing className="w-6 text-muted-foreground" />
                                </div>
                                <div className="flex min-w-0 flex-1 flex-col">
                                    <div className="truncate body">{fileUploadName}</div>
                                </div>
                                <div className="mx-2 flex items-center body-secondary">
                                    {t('Uploading...')}
                                </div>
                            </div>
                        </Skeleton>
                    )}
                    {selectedFiles?.map((file, index) => (
                        <div key={index} className="group flex w-full items-center gap-4 pt-6 pb-3">
                            <div className="flex w-8 items-center justify-center">
                                <FileChartColumnIncreasing className="w-6 text-muted-foreground" />
                            </div>
                            <div className="flex min-w-0 flex-1 flex-col">
                                <div className="truncate body">{file.filename}</div>
                                <div className="truncate caption-01">
                                    {t('File size: {{size}}', {
                                        size: formatFileSize(file?.size_bytes || 0),
                                    })}
                                </div>
                            </div>
                            <div className="ml-2 flex items-center">
                                <XIcon
                                    className="size-4 cursor-pointer text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100"
                                    onClick={event => {
                                        event.stopPropagation();
                                        if (isDisabled) {
                                            return;
                                        }
                                        onRemove(file.uuid);
                                    }}
                                />
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            <ConnectedSourcesDialog
                open={isConnectedSourcesOpen}
                onOpenChange={setIsConnectedSourcesOpen}
                onFileSelect={handleExternalFileSelect}
                isUploading={isExternalFileUploading}
            />
        </>
    );
}
