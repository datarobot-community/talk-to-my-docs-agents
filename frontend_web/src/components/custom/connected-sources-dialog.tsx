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
import { CloudUpload, FileIcon, FolderIcon, ExternalLink, Search } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

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
    const { connectedSources, hasConnectedSources } = useConnectedSources();
    const [selectedGoogleFolder, setSelectedGoogleFolder] = useState<string | undefined>();
    const [selectedBoxFolder, setSelectedBoxFolder] = useState<string>('0');
    const [googleSearchQuery, setGoogleSearchQuery] = useState<string>('');
    const [boxSearchQuery, setBoxSearchQuery] = useState<string>('');
    const navigate = useNavigate();

    const { data: googleFiles, isLoading: isLoadingGoogle } = useGoogleFiles(
        selectedGoogleFolder,
        open && connectedSources.some(s => s.type === 'google')
    );

    const { data: boxFiles, isLoading: isLoadingBox } = useBoxFiles(
        selectedBoxFolder,
        open && connectedSources.some(s => s.type === 'box')
    );

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
            handleDialogClose(false);
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

    const renderFileList = (
        files: ExternalFile[] | undefined,
        source: 'google' | 'box',
        isLoading: boolean
    ) => {
        if (isLoading) {
            return <div className="p-4 text-center text-gray-500">Loading files...</div>;
        }

        if (!files || files.length === 0) {
            return <div className="p-4 text-center text-gray-500">No files found</div>;
        }

        const searchQuery = source === 'google' ? googleSearchQuery : boxSearchQuery;
        const setSearchQuery = source === 'google' ? setGoogleSearchQuery : setBoxSearchQuery;

        // Filter files based on search query
        const filteredFiles = files.filter(file =>
            file.name.toLowerCase().includes(searchQuery.toLowerCase())
        );

        return (
            <div className="flex flex-col h-full">
                {/* Search Box */}
                <div className="p-2 border-b flex-shrink-0">
                    <div className="relative">
                        <Search className="absolute left-2 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
                        <Input
                            placeholder={`Search ${source} files...`}
                            value={searchQuery}
                            onChange={e => setSearchQuery(e.target.value)}
                            className="pl-8"
                        />
                    </div>
                </div>

                {/* File Count */}
                <div className="text-sm text-gray-600 p-2 border-b bg-gray-50 flex-shrink-0">
                    {searchQuery ? (
                        <>
                            Showing {filteredFiles.length} of {files.length} items
                        </>
                    ) : (
                        <>Showing {files.length} items</>
                    )}
                </div>

                {/* File List */}
                <div className="flex-1 overflow-hidden">
                    <ScrollArea className="h-full" type="always">
                        <div className="p-2">
                            {filteredFiles.length === 0 ? (
                                <div className="p-4 text-center text-gray-500">
                                    No files match "{searchQuery}"
                                </div>
                            ) : (
                                filteredFiles.map(file => (
                                    <div
                                        key={file.id}
                                        className={`flex items-center gap-3 p-3 hover:bg-gray-600 cursor-pointer border-b border-gray-100 last:border-b-0 ${
                                            isUploading ? 'opacity-50' : ''
                                        }`}
                                        onClick={() =>
                                            !isUploading && handleFileSelect(file, source)
                                        }
                                    >
                                        {file.type === 'folder' ? (
                                            <FolderIcon className="w-4 h-4 text-blue-500 flex-shrink-0" />
                                        ) : file.type === 'web_link' ? (
                                            <ExternalLink className="w-4 h-4 text-green-500 flex-shrink-0" />
                                        ) : (
                                            <FileIcon className="w-4 h-4 text-gray-500 flex-shrink-0" />
                                        )}
                                        <span className="flex-1 text-sm truncate">{file.name}</span>
                                        <span className="text-xs text-gray-400 flex-shrink-0">
                                            {file.type}
                                        </span>
                                        {isUploading && (
                                            <div className="flex items-center gap-1">
                                                <div className="w-3 h-3 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                                                <span className="text-xs text-blue-500">
                                                    Uploading...
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
            <SheetContent className="w-[400px] sm:w-[540px]">
                <SheetHeader>
                    <SheetTitle className="flex items-center gap-2">
                        <CloudUpload className="w-5 h-5" />
                        Upload from Connected Source
                        {isUploading && (
                            <div className="flex items-center gap-2 ml-2">
                                <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                                <span className="text-sm text-blue-500">Uploading...</span>
                            </div>
                        )}
                    </SheetTitle>
                </SheetHeader>

                {!hasConnectedSources ? (
                    <div className="flex flex-col items-center justify-center py-8 space-y-4">
                        <CloudUpload className="w-12 h-12 text-gray-400" />
                        <div className="text-center">
                            <h3 className="text-lg font-medium text-gray-900">
                                No Connected Sources
                            </h3>
                            <p className="text-sm text-gray-500 mt-1">
                                Connect to Google Drive or Box to upload files from your cloud
                                storage.
                            </p>
                        </div>
                        <Button onClick={goToSettings} className="mt-4">
                            Connect Sources
                        </Button>
                    </div>
                ) : (
                    <div className="mt-6 flex flex-col h-[calc(100vh-200px)]">
                        <Tabs
                            defaultValue={connectedSources[0]?.type}
                            className="w-full flex flex-col h-full"
                        >
                            <TabsList
                                className={`grid w-full ${connectedSources.length === 1 ? 'grid-cols-1' : 'grid-cols-2'} flex-shrink-0`}
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
                                    className="mt-4 flex-1 flex flex-col overflow-hidden"
                                >
                                    <div className="flex flex-col h-full">
                                        {/* Back button */}
                                        <div className="flex-shrink-0 mb-2">
                                            {source.type === 'google' && selectedGoogleFolder && (
                                                <Button
                                                    variant="outline"
                                                    size="sm"
                                                    onClick={() => {
                                                        setSelectedGoogleFolder(undefined);
                                                        setGoogleSearchQuery('');
                                                    }}
                                                >
                                                    ← Back to root
                                                </Button>
                                            )}
                                            {source.type === 'box' && selectedBoxFolder !== '0' && (
                                                <Button
                                                    variant="outline"
                                                    size="sm"
                                                    onClick={() => {
                                                        setSelectedBoxFolder('0');
                                                        setBoxSearchQuery('');
                                                    }}
                                                >
                                                    ← Back to root
                                                </Button>
                                            )}
                                        </div>

                                        {/* File list - takes remaining height */}
                                        <div className="flex-1 border rounded-md overflow-hidden min-h-0">
                                            {source.type === 'google' &&
                                                renderFileList(
                                                    googleFiles?.files,
                                                    'google',
                                                    isLoadingGoogle
                                                )}
                                            {source.type === 'box' &&
                                                renderFileList(
                                                    boxFiles?.files,
                                                    'box',
                                                    isLoadingBox
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
