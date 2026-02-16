import React, { useState } from 'react';
import { toast } from 'sonner';
import Dropzone, { type FileRejection } from 'react-dropzone';
import fileUpload from '@/assets/file_upload.svg';
import { XIcon, Plus, FileChartColumnIncreasing } from 'lucide-react';
import { Button } from '@/components/ui/button.tsx';
import { Progress } from '@/components/ui/progress';
import { ScrollArea } from '@/components/ui/scroll-area';
import { ConfirmDialog } from '@/components/custom/confirm-dialog';
import { FileSchema, useFileUploadMutation } from '@/api/knowledge-bases/hooks';
import { getApiErrorMessage } from '@/api/utils';
import { FileActionMenu } from '@/components/custom/file-action-menu.tsx';
import { formatFileSize } from '@/lib/utils';
import { useTranslation } from '@/lib/i18n';

interface FileUploaderProps {
    maxSize?: number;
    accept?: { [key: string]: string[] };
    onFilesChange: (files: File[]) => void;
    onDeleteFile: (fileUuid: string) => Promise<void> | void;
    baseUuid?: string;
    onUploadComplete?: () => void;
    existingFiles?: FileSchema[];
}

export const FileUploader: React.FC<FileUploaderProps> = ({
    maxSize = 1024 * 1024 * 200,
    accept = {
        'text/plain': ['.txt'],
        'application/pdf': ['.pdf'],
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
        'text/markdown': ['.md'],
        'application/vnd.openxmlformats-officedocument.presentationml.presentation': ['.pptx'],
        'text/csv': ['.csv'],
    },
    onFilesChange,
    baseUuid,
    onUploadComplete,
    onDeleteFile,
    existingFiles = [],
}) => {
    const { t } = useTranslation();
    const [files, setFiles] = useState<File[]>([]);
    const [filesToRemove, setFilesToRemove] = useState<FileSchema | undefined>();
    const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);

    const {
        mutate: uploadFiles,
        isPending: isUploading,
        progress,
    } = useFileUploadMutation({
        baseUuid,
        onSuccess: () => {
            toast.success(t('Files uploaded successfully'));
            setFiles([]);
            onFilesChange([]);
            if (onUploadComplete) {
                onUploadComplete();
            }
        },
        onError: error => {
            toast.error(getApiErrorMessage(error, t('Upload failed')));
        },
    });

    const onDrop = React.useCallback(
        (acceptedFiles: File[], rejectedFiles: FileRejection[]) => {
            const newFiles = acceptedFiles.map(file =>
                Object.assign(file, {
                    preview: URL.createObjectURL(file),
                })
            );

            const updatedFiles = files ? [...files, ...newFiles] : newFiles;

            setFiles(updatedFiles);
            onFilesChange(updatedFiles);

            if (rejectedFiles.length > 0) {
                rejectedFiles.forEach(({ file }) => {
                    console.error(t('File {{name}} was rejected', { name: file.name }));
                });
            }
        },
        [files, onFilesChange]
    );

    function onRemove(index: number) {
        if (!files) return;
        const newFiles = files.filter((_, i) => i !== index);
        setFiles(newFiles);
        onFilesChange(newFiles);
    }

    const handleUpload = () => {
        if (files.length > 0) {
            uploadFiles({ files });
        }
    };

    const currentProgress = progress;

    const handleConfirmDelete = async () => {
        const fileUuid = filesToRemove?.uuid;
        if (!fileUuid) {
            setFilesToRemove(undefined);
            return;
        }

        setIsConfirmingDelete(true);
        try {
            await Promise.resolve(onDeleteFile(fileUuid));
            setFilesToRemove(undefined);
        } catch (error) {
            console.error('Failed to delete file', error);
        } finally {
            setIsConfirmingDelete(false);
        }
    };

    return (
        <div className="w-full">
            <Dropzone onDrop={onDrop} maxSize={maxSize} accept={accept}>
                {({ getRootProps, getInputProps }) => (
                    <div
                        {...getRootProps()}
                        onClick={event => {
                            event.stopPropagation();
                        }}
                        className="mt-6 min-h-[300px] w-full rounded-lg border border-dashed p-4"
                    >
                        <input data-testid="file-input" {...getInputProps()} />
                        <div className="flex items-center justify-between">
                            <span className="heading-04">{t('Upload Files')}</span>
                            <Button
                                data-testid="add-files-button"
                                {...getRootProps()}
                                className="cursor-pointer"
                                type="button"
                                size="sm"
                                disabled={isUploading}
                            >
                                <Plus className="mr-2 size-4" />
                                {t('Add files')}
                            </Button>
                        </div>

                        {currentProgress !== 100 && currentProgress !== 0 && (
                            <Progress value={currentProgress} className="mt-4 h-2" />
                        )}
                        <ScrollArea className="mt-4 scrollbar-thin w-full border-t border-primary/10">
                            <div className="max-h-[calc(100vh-400px)] min-h-[360px]">
                                {!files.length && !existingFiles.length && (
                                    <p className="body-secondary p-6 text-center">
                                        <img
                                            src={fileUpload}
                                            alt={t('File Upload')}
                                            className="mx-auto mb-4 size-16"
                                        />
                                        {t(
                                            'Drag and drop documents here. Supported formats: TXT, PDF, DOCX, MD, PPTX, CSV.'
                                        )}
                                    </p>
                                )}
                                {files.length > 0 && (
                                    <div className="border-b border-secondary-foreground pb-4">
                                        {/* New files to upload */}
                                        {files.map((file, index) => (
                                            <div
                                                key={`new-${index}`}
                                                className="group flex w-full items-center gap-4 pt-4 pr-4"
                                            >
                                                <div className="flex w-8 items-center justify-center">
                                                    <FileChartColumnIncreasing className="w-6 text-muted-foreground" />
                                                </div>
                                                <div className="min-w-0 flex-1">
                                                    <div className="truncate body leading-tight">
                                                        {file.name}
                                                    </div>
                                                    <div className="truncate caption-01 leading-tight">
                                                        {t('File size: {{size}}', {
                                                            size: formatFileSize(file?.size || 0),
                                                        })}
                                                    </div>
                                                </div>
                                                <div className="ml-2 flex items-center">
                                                    <XIcon
                                                        className="size-4 cursor-pointer text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100"
                                                        onClick={event => {
                                                            event.stopPropagation();
                                                            onRemove(index);
                                                        }}
                                                    />
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}

                                {/* Existing files */}
                                {existingFiles.map((file, index) => {
                                    return (
                                        <div
                                            key={`existing-${index}`}
                                            className="group flex w-full items-center gap-4 border-secondary-foreground py-4 pr-1"
                                        >
                                            <div className="flex w-8 items-center justify-center">
                                                <FileChartColumnIncreasing className="w-6 text-link" />
                                            </div>
                                            <div className="w-0 flex-1">
                                                <div className="truncate body leading-tight">
                                                    {file.filename}
                                                </div>
                                                <div className="truncate caption-01 leading-tight">
                                                    {t('Added: {{date}}{{size}}', {
                                                        date: new Date(
                                                            file.added
                                                        ).toLocaleDateString(),
                                                        size: file.size_bytes
                                                            ? ` • ${formatFileSize(file?.size_bytes || 0)}`
                                                            : '',
                                                    })}
                                                </div>
                                            </div>
                                            <FileActionMenu
                                                file={file}
                                                onDelete={setFilesToRemove}
                                            />
                                        </div>
                                    );
                                })}
                            </div>
                        </ScrollArea>
                    </div>
                )}
            </Dropzone>

            {files.length > 0 && (
                <div className="mt-4 flex justify-end gap-2">
                    <Button
                        variant="secondary"
                        onClick={() => {
                            setFiles([]);
                            onFilesChange([]);
                        }}
                        disabled={isUploading}
                    >
                        {t('Clear')}
                    </Button>
                    <Button
                        data-testid="upload-button"
                        onClick={handleUpload}
                        disabled={isUploading || files.length === 0}
                    >
                        {isUploading
                            ? currentProgress === 100
                                ? t('Saving...')
                                : t('Uploading...')
                            : t('Upload {{count}} file', {
                                  count: files.length,
                                  plural: 'Upload {{count}} files',
                              })}
                    </Button>
                </div>
            )}
            <ConfirmDialog
                open={Boolean(filesToRemove)}
                confirmButtonText={t('Delete')}
                onOpenChange={open => {
                    if (!open) {
                        if (isConfirmingDelete) {
                            return;
                        }
                        setFilesToRemove(undefined);
                    }
                }}
                title={t('Delete File: {{filename}}', {
                    filename: filesToRemove?.filename || '',
                })}
                confirmLoading={isConfirmingDelete}
                confirmLoadingText={t('Deleting...')}
                onConfirm={handleConfirmDelete}
            >
                <div>{t('Are you sure you want to delete this file?')}</div>
            </ConfirmDialog>
        </div>
    );
};
