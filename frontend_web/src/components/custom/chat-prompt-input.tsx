import { useCallback, useState, useRef, useEffect } from 'react';
import { useParams } from 'react-router-dom';

import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import {
    FileChartColumnIncreasing,
    ArrowUpFromLine,
    BookOpenText,
    CloudUpload,
    Send,
    XIcon,
    Plus,
    Info,
} from 'lucide-react';
import { usePostMessage } from '@/api/chat/hooks.ts';
import { cn } from '@/lib/utils.ts';
import {
    DropdownMenu,
    DropdownMenuTrigger,
    DropdownMenuContent,
    DropdownMenuItem,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import {
    useFileUploadMutation,
    useListKnowledgeBases,
    FileSchema,
} from '@/api/knowledge-bases/hooks';
import { ConnectedSourcesDialog } from '@/components/custom/connected-sources-dialog';
import { ExternalFile, useExternalFileUploadMutation } from '@/api/external-files';
import { useAppState } from '@/state';
import { AGENT_MODEL } from '@/api/chat/constants';
import { useNavigate } from 'react-router-dom';
import { ROUTES } from '@/pages/routes.ts';

export function ChatPromptInput({
    classNames,
    setPendingMessage,
    isPendingMessage,
}: {
    classNames?: string;
    isPendingMessage: boolean;
    setPendingMessage: (value: boolean) => void;
}) {
    const { chatId } = useParams<{ chatId: string }>();
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [message, setMessage] = useState<string>('');
    const { mutateAsync } = usePostMessage({ chatId });
    const navigate = useNavigate();
    const { selectedLlmModel, selectedKnowledgeBase, setSelectedKnowledgeBase } = useAppState();
    const { data: bases = [], isFetched: isKnowledgeBasesFetched } = useListKnowledgeBases();
    const [files, setFiles] = useState<FileSchema[]>();
    const [isConnectedSourcesOpen, setIsConnectedSourcesOpen] = useState(false);
    const [isComposing, setIsComposing] = useState(false);
    const { mutate } = useFileUploadMutation({
        onSuccess: data => {
            setFiles(data);
        },
        onError: error => {
            console.error('Error uploading file:', error);
        },
    });

    useEffect(() => {
        if (
            isKnowledgeBasesFetched &&
            selectedKnowledgeBase &&
            !bases.some(base => base.uuid === selectedKnowledgeBase.uuid)
        ) {
            setSelectedKnowledgeBase(null);
        }
    }, [selectedKnowledgeBase, bases, isKnowledgeBasesFetched, setSelectedKnowledgeBase]);

    const { mutate: mutateExternalFile, isPending: isExternalFileUploading } =
        useExternalFileUploadMutation({
            onSuccess: data => {
                setFiles(data);
            },
            onError: error => {
                console.error('Error uploading external file:', error);
            },
        });

    const isAgentModel = selectedLlmModel.model === AGENT_MODEL;

    const handleMenuClick = () => {
        fileInputRef.current?.click();
    };

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const uploadedFile = e.target.files;
        if (uploadedFile && uploadedFile[0]) {
            mutate({ files: [uploadedFile[0]] });
        }
    };

    const handleExternalFileSelect = (file: ExternalFile, source: 'google' | 'box') => {
        // Upload the external file using the new API
        mutateExternalFile({ file, source });
    };

    const handleConnectedSourcesClick = () => {
        setIsConnectedSourcesOpen(true);
    };

    const handleKnowledgeBaseSelect = async (baseUuid: string) => {
        const selectedBase = bases.find(base => base.uuid === baseUuid);
        console.log('Selecting knowledge base:', selectedBase?.title, 'UUID:', baseUuid);
        setSelectedKnowledgeBase(selectedBase || null);
    };

    const handleAddKnowledgeBase = () => {
        // Navigate to the new base page
        navigate(ROUTES.ADD_KNOWLEDGE_BASE);
    };

    const handleSubmit = useCallback(async () => {
        if (message) {
            setPendingMessage(true);
            try {
                // Send file IDs instead of content
                const context = files?.length
                    ? { fileIds: files.map(file => file.uuid) }
                    : undefined;
                // Send only knowledge base ID instead of full knowledge base object
                const knowledgeBaseId = selectedKnowledgeBase
                    ? selectedKnowledgeBase.uuid
                    : undefined;
                await mutateAsync({
                    message,
                    context,
                    knowledgeBaseId,
                });
            } finally {
                setMessage('');
                setPendingMessage(false);
            }
        }
    }, [mutateAsync, message, setMessage, setPendingMessage, files, selectedKnowledgeBase]);

    const handleEnterPress = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === 'Enter' && !e.shiftKey && !isComposing) {
            e.preventDefault();
            handleSubmit();
        }
    };

    function onRemove(index: number) {
        if (!files) return;
        const newFiles = files.filter((_, i) => i !== index);
        setFiles(newFiles);
    }

    return (
        <>
            <div
                className={cn(
                    isPendingMessage ? 'cursor-wait opacity-70' : '',
                    'transition-all',
                    'justify-items-center p-5 w-2xl',
                    classNames
                )}
                data-testid="chat-prompt-input"
            >
                <Textarea
                    disabled={isPendingMessage}
                    onChange={e => setMessage(e.target.value)}
                    placeholder="Ask anything..."
                    value={message}
                    className={cn(
                        isPendingMessage && 'pointer-events-none',
                        'resize-none rounded-none',
                        'dark:bg-muted border-gray-700'
                    )}
                    onKeyDown={handleEnterPress}
                    onCompositionStart={() => setIsComposing(true)}
                    onCompositionEnd={() => setIsComposing(false)}
                    data-testid="chat-prompt-input-textarea"
                />
                <div className="w-full p-1 border border-t-0 border-gray-700">
                    <div className="flex items-center justify-between h-12">
                        <div className="flex gap-1 items-center">
                            <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                    <Button
                                        className="justify-self-end cursor-pointer"
                                        variant="ghost"
                                        size="icon"
                                        onClick={() => true}
                                        disabled={isPendingMessage}
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
                                        Upload from computer
                                    </DropdownMenuItem>
                                    <DropdownMenuItem
                                        onClick={handleConnectedSourcesClick}
                                        className="cursor-pointer"
                                    >
                                        <CloudUpload />
                                        Upload from connected source
                                    </DropdownMenuItem>
                                    {/* Knowledge base selection for all models */}
                                    {bases.length > 0 || selectedKnowledgeBase ? (
                                        [
                                            ...bases.map(base => (
                                                <DropdownMenuItem
                                                    key={base.uuid}
                                                    onClick={() =>
                                                        handleKnowledgeBaseSelect(base.uuid)
                                                    }
                                                    className={cn(
                                                        'cursor-pointer',
                                                        selectedKnowledgeBase?.uuid === base.uuid &&
                                                            'bg-primary/10 text-primary font-semibold'
                                                    )}
                                                >
                                                    <BookOpenText
                                                        className={cn(
                                                            selectedKnowledgeBase?.uuid ===
                                                                base.uuid && 'text-primary'
                                                        )}
                                                    />
                                                    <div className="flex flex-col ml-2">
                                                        <span
                                                            className={cn(
                                                                'font-medium',
                                                                selectedKnowledgeBase?.uuid ===
                                                                    base.uuid &&
                                                                    'font-semibold text-primary'
                                                            )}
                                                        >
                                                            {base.title}
                                                        </span>
                                                        <span className="text-xs text-gray-500 truncate">
                                                            {base.files.length} file
                                                            {base.files.length !== 1
                                                                ? 's'
                                                                : ''} •{' '}
                                                            {base.token_count.toLocaleString()}{' '}
                                                            tokens
                                                        </span>
                                                        {!isAgentModel && (
                                                            <span className="text-xs text-amber-600 font-medium">
                                                                ⚠ High token usage possible
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
                                            Add forecast view
                                        </DropdownMenuItem>
                                    )}
                                </DropdownMenuContent>
                            </DropdownMenu>
                            <Info className="h-4 text-gray-400" />
                            <p className="h-4 text-base text-gray-400 leading-none">
                                Upload a file or select a forecast view
                            </p>
                        </div>
                        <Input
                            ref={fileInputRef}
                            type="file"
                            className="hidden"
                            accept=".txt,.pdf,.docx,.md,.pptx,.csv"
                            onChange={handleFileChange}
                        />
                        <Button
                            className="justify-self-end cursor-pointer"
                            variant="ghost"
                            size="icon"
                            onClick={handleSubmit}
                            data-testid="chat-prompt-input-submit"
                            disabled={isPendingMessage}
                        >
                            <Send />
                        </Button>
                    </div>
                    {selectedKnowledgeBase && (
                        <div className="gap-2 mt-2 bg-accent/30 p-2 rounded w-1/2">
                            <div className="flex items-center spacebetween">
                                <p
                                    className="text-base truncate"
                                    title={selectedKnowledgeBase.title}
                                >
                                    {selectedKnowledgeBase.title}
                                </p>
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    className="ml-auto"
                                    onClick={() => setSelectedKnowledgeBase(null)}
                                >
                                    <XIcon />
                                </Button>
                            </div>
                            <div>
                                <div className=" flex text-sm items-center text-gray-600 gap-2 mb-2">                                <div className="bg-indigo-400 rounded-full px-2 py-1 text-xs text-gray-900 vertical-align-middle">
                                    Forecast view
                                </div>
                                    <div className="text-xs text-gray-500">
                                        {selectedKnowledgeBase.files.length} file
                                        {selectedKnowledgeBase.files.length !== 1 ? 's' : ''} •{' '}
                                        {selectedKnowledgeBase.token_count.toLocaleString()} tokens
                                    </div>
                                </div>
                                {!isAgentModel && (
                                    <div className="text-xs text-amber-600 font-medium">
                                        ⚠ High token usage possible
                                    </div>
                                )}
                            </div>
                        </div>
                    )}
                    {files?.map((file, index) => (
                        <div
                            key={index}
                            className="group flex items-center pt-6 pb-3 gap-4 w-full "
                        >
                            <div className="flex justify-center items-center w-8">
                                <FileChartColumnIncreasing className="w-6 text-muted-foreground" />
                            </div>
                            <div className="flex flex-col flex-1 min-w-0">
                                <div className="text-sm font-normal leading-tight truncate">
                                    {file.filename}
                                </div>
                                <div className="text-xs text-gray-400 leading-tight truncate">
                                    File size: {((file?.size_bytes || 0) / 1024 / 1024).toFixed(2)}{' '}
                                    MB
                                </div>
                            </div>
                            <div className="flex items-center ml-2">
                                <XIcon
                                    className="w-4 h-4 cursor-pointer text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity"
                                    onClick={event => {
                                        event.stopPropagation();
                                        onRemove(index);
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
