import { useState } from 'react';
import {
    useConnectedSources,
    useGoogleFiles,
    useBoxFiles,
    ExternalFile,
} from '@/api/external-files';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Heading } from '@/components/ui/heading';
import {
    CloudUpload,
    FileIcon,
    FolderIcon,
    ExternalLink,
    Search,
    AlertCircle,
    RefreshCw,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { AxiosError } from 'axios';
import { useTranslation } from '@/lib/i18n';

interface ConnectedSourcesDialogProps {
    onFileSelect: (file: ExternalFile, source: 'google' | 'box') => void;
    open: boolean;
    onOpenChange: (open: boolean) => void;
    isUploading?: boolean;
}

export function ConnectedSourcesDialog({
    onFileSelect,
    open,
    onOpenChange,
    isUploading = false,
}: ConnectedSourcesDialogProps) {
    const { t } = useTranslation();
    const { connectedSources, hasConnectedSources } = useConnectedSources();
    const [selectedGoogleFolder, setSelectedGoogleFolder] = useState<string | undefined>();
    const [selectedBoxFolder, setSelectedBoxFolder] = useState<string>('0');
    const [googleSearchQuery, setGoogleSearchQuery] = useState<string>('');
    const [boxSearchQuery, setBoxSearchQuery] = useState<string>('');
    const navigate = useNavigate();

    const {
        data: googleFiles,
        isLoading: isLoadingGoogle,
        error: googleError,
        refetch: refetchGoogle,
    } = useGoogleFiles(
        selectedGoogleFolder,
        open && connectedSources.some(s => s.type === 'google')
    );

    const {
        data: boxFiles,
        isLoading: isLoadingBox,
        error: boxError,
        refetch: refetchBox,
    } = useBoxFiles(selectedBoxFolder, open && connectedSources.some(s => s.type === 'box'));

    const handleFileSelect = (file: ExternalFile, source: 'google' | 'box') => {
        if (file.type === 'folder') {
            // Clear search when navigating to a new folder
            if (source === 'google') {
                setSelectedGoogleFolder(file.id);
                setGoogleSearchQuery('');
            } else {
                setSelectedBoxFolder(file.id);
                setBoxSearchQuery('');
            }
        } else if (file.type === 'file') {
            onFileSelect(file, source);
        }
    };

    const goToSettings = () => {
        handleDialogClose(false);
        navigate('/settings/sources');
    };

    const handleDialogClose = (open: boolean) => {
        if (!open) {
            // Reset search queries when dialog closes
            setGoogleSearchQuery('');
            setBoxSearchQuery('');
        }
        onOpenChange(open);
    };

    // Helper function to get error message from different error types
    const getErrorMessage = (error: unknown): string => {
        if (typeof error === 'object' && error && 'response' in error) {
            const axiosError = error as AxiosError;

            // Handle authentication errors specifically
            if (axiosError.response?.status === 401) {
                if (
                    axiosError.response?.data &&
                    typeof axiosError.response.data === 'object' &&
                    'detail' in axiosError.response.data
                ) {
                    const detail = (axiosError.response.data as { detail: unknown }).detail;
                    // Handle ErrorSchema structure: { code: string, message: string }
                    if (typeof detail === 'object' && detail && 'message' in detail) {
                        return (detail as { message: string }).message;
                    }
                    // Handle plain string detail
                    if (typeof detail === 'string') {
                        return detail;
                    }
                }
                return t('Authentication failed. Please reconnect your account.');
            }

            // Handle authorization errors
            if (axiosError.response?.status === 403) {
                return t('Access denied. Please check your account permissions.');
            }
        }

        return t('Unable to connect. Please try again or reconnect your account.');
    };

    // Helper function to determine if we should show retry vs reconnect
    const shouldShowReconnect = (error: unknown): boolean => {
        if (typeof error === 'object' && error && 'response' in error) {
            const axiosError = error as AxiosError;
            return axiosError.response?.status === 401 || axiosError.response?.status === 403;
        }
        return false;
    };

    const renderFileList = (
        files: ExternalFile[] | undefined,
        source: 'google' | 'box',
        isLoading: boolean,
        error: unknown,
        refetch: () => void
    ) => {
        // Handle error state
        if (error) {
            const errorMessage = getErrorMessage(error);
            const needsReconnect = shouldShowReconnect(error);

            return (
                <div className="space-y-4 p-4">
                    <Alert variant="destructive">
                        <AlertCircle className="size-4" />
                        <AlertDescription>
                            <div>
                                <p className="mn-label">
                                    {t('Unable to connect to {{source}}', {
                                        source: source === 'google' ? 'Google Drive' : 'Box',
                                    })}
                                </p>
                                <p className="mt-1 body">{errorMessage}</p>
                            </div>
                        </AlertDescription>
                    </Alert>
                    <div className="flex justify-center">
                        {needsReconnect ? (
                            <Button onClick={goToSettings} variant="secondary" size="sm">
                                {t('Reconnect Account')}
                            </Button>
                        ) : (
                            <Button
                                onClick={refetch}
                                variant="secondary"
                                size="sm"
                                className="flex items-center gap-2"
                            >
                                <RefreshCw className="size-3" />
                                {t('Try Again')}
                            </Button>
                        )}
                    </div>
                </div>
            );
        }

        if (isLoading) {
            return <div className="body-secondary p-4 text-center">{t('Loading files...')}</div>;
        }

        if (!files || files.length === 0) {
            return <div className="body-secondary p-4 text-center">{t('No files found')}</div>;
        }

        const searchQuery = source === 'google' ? googleSearchQuery : boxSearchQuery;
        const setSearchQuery = source === 'google' ? setGoogleSearchQuery : setBoxSearchQuery;

        // Filter files based on search query
        const filteredFiles = files.filter(file =>
            file.name.toLowerCase().includes(searchQuery.toLowerCase())
        );

        return (
            <div className="flex h-full flex-col gap-2 p-2">
                {/* Search Box */}
                <div className="shrink-0">
                    <div className="relative">
                        <Search className="pointer-events-none absolute top-1/2 left-2 size-4 -translate-y-1/2 text-muted-foreground select-none" />
                        <Input
                            placeholder={t('Search {{source}} files...', { source })}
                            value={searchQuery}
                            onChange={e => setSearchQuery(e.target.value)}
                            className="pl-8"
                        />
                    </div>
                </div>

                {/* File Count */}
                <div className="shrink-0 border-b body-secondary py-2">
                    {searchQuery ? (
                        <>
                            {t('Showing {{filtered}} of {{total}} items', {
                                filtered: filteredFiles.length,
                                total: files.length,
                            })}
                        </>
                    ) : (
                        <>
                            {t('Showing {{total}} items', {
                                total: files.length,
                            })}
                        </>
                    )}
                </div>

                {/* File List */}
                <div className="flex-1 overflow-hidden">
                    <ScrollArea className="h-full" type="always">
                        <div>
                            {filteredFiles.length === 0 ? (
                                <div className="body-secondary p-4 text-center">
                                    {t('No files match "{{query}}"', {
                                        query: searchQuery,
                                    })}
                                </div>
                            ) : (
                                filteredFiles.map(file => (
                                    <div
                                        key={file.id}
                                        className={`flex cursor-pointer items-center gap-3 border-b p-3 last:border-b-0 hover:bg-secondary ${
                                            isUploading ? 'opacity-50' : ''
                                        }`}
                                        onClick={() =>
                                            !isUploading && handleFileSelect(file, source)
                                        }
                                    >
                                        {file.type === 'folder' ? (
                                            <FolderIcon className="size-4 shrink-0 text-link" />
                                        ) : file.type === 'web_link' ? (
                                            <ExternalLink className="size-4 shrink-0 text-success" />
                                        ) : (
                                            <FileIcon className="size-4 shrink-0 text-muted-foreground" />
                                        )}
                                        <span className="flex-1 truncate body">{file.name}</span>
                                        <span className="shrink-0 caption-01">{file.type}</span>
                                        {isUploading && (
                                            <div className="flex items-center gap-1">
                                                <div className="size-3 animate-spin rounded-full border-2 border-link border-t-transparent" />
                                                <span className="caption-01 text-link">
                                                    {t('Uploading...')}
                                                </span>
                                            </div>
                                        )}
                                    </div>
                                ))
                            )}
                        </div>
                    </ScrollArea>
                </div>
            </div>
        );
    };

    return (
        <Sheet open={open} onOpenChange={handleDialogClose}>
            <SheetContent className="w-[400px] shrink p-2 sm:w-[540px]">
                <SheetHeader>
                    <SheetTitle className="flex items-center gap-2">
                        <CloudUpload className="size-5" />
                        {t('Upload from Connected Source')}
                        {isUploading && (
                            <div className="ml-2 flex items-center gap-2">
                                <div className="size-4 animate-spin rounded-full border-2 border-link border-t-transparent" />
                                <span className="body text-link">{t('Uploading...')} </span>
                            </div>
                        )}
                    </SheetTitle>
                </SheetHeader>

                {!hasConnectedSources ? (
                    <div className="flex flex-col items-center justify-center space-y-4 py-8">
                        <CloudUpload className="size-12 text-muted-foreground" />
                        <div className="text-center">
                            <Heading level={3}>{t('No Connected Sources')}</Heading>
                            <p className="mt-1 body-secondary">
                                {t(
                                    'Connect to Google Drive or Box to upload files from your cloud storage.'
                                )}
                            </p>
                        </div>
                        <Button onClick={goToSettings} className="mt-4">
                            {t('Connect Sources')}
                        </Button>
                    </div>
                ) : (
                    <div className="flex grow flex-col overflow-y-scroll">
                        <Tabs
                            defaultValue={connectedSources[0]?.type}
                            className="flex size-full flex-col"
                        >
                            <TabsList
                                className={`grid w-full ${connectedSources.length === 1 ? 'grid-cols-1' : 'grid-cols-2'} shrink-0`}
                            >
                                {connectedSources.map(source => (
                                    <TabsTrigger key={source.id} value={source.type}>
                                        {source.name}
                                    </TabsTrigger>
                                ))}
                            </TabsList>

                            {connectedSources.map(source => (
                                <TabsContent
                                    key={source.id}
                                    value={source.type}
                                    className="mt-4 flex flex-1 flex-col overflow-hidden"
                                >
                                    <div className="flex h-full flex-col">
                                        {/* Back button */}
                                        <div className="mb-2 shrink-0">
                                            {source.type === 'google' && selectedGoogleFolder && (
                                                <Button
                                                    variant="secondary"
                                                    size="sm"
                                                    onClick={() => {
                                                        setSelectedGoogleFolder(undefined);
                                                        setGoogleSearchQuery('');
                                                    }}
                                                >
                                                    {t('← Back to root')}
                                                </Button>
                                            )}
                                            {source.type === 'box' && selectedBoxFolder !== '0' && (
                                                <Button
                                                    variant="secondary"
                                                    size="sm"
                                                    onClick={() => {
                                                        setSelectedBoxFolder('0');
                                                        setBoxSearchQuery('');
                                                    }}
                                                >
                                                    {t('← Back to root')}
                                                </Button>
                                            )}
                                        </div>

                                        {/* File list - takes remaining height */}
                                        <div className="min-h-0 flex-1 overflow-hidden rounded-md border">
                                            {source.type === 'google' &&
                                                renderFileList(
                                                    googleFiles?.files,
                                                    'google',
                                                    isLoadingGoogle,
                                                    googleError,
                                                    refetchGoogle
                                                )}
                                            {source.type === 'box' &&
                                                renderFileList(
                                                    boxFiles?.files,
                                                    'box',
                                                    isLoadingBox,
                                                    boxError,
                                                    refetchBox
                                                )}
                                        </div>
                                    </div>
                                </TabsContent>
                            ))}
                        </Tabs>
                    </div>
                )}
            </SheetContent>
        </Sheet>
    );
}
