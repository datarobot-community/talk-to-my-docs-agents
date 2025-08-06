import { AxiosProgressEvent } from 'axios';

import apiClient from '../apiClient';
import {
    KnowledgeBaseSchema,
    KnowledgeBaseListResponse,
    KnowledgeBaseWithContent,
    KnowledgeBaseCreateRequest,
    KnowledgeBaseUpdateRequest,
    FileSchema,
} from './types';

// Knowledge Base API functions
export async function listKnowledgeBases(signal?: AbortSignal): Promise<KnowledgeBaseSchema[]> {
    const response = await apiClient.get<KnowledgeBaseListResponse>('/v1/knowledge-bases/', {
        signal,
    });
    return response.data.knowledge_bases;
}

export async function getKnowledgeBase(
    knowledgeBaseUuid: string,
    signal?: AbortSignal
): Promise<KnowledgeBaseWithContent> {
    const response = await apiClient.get<KnowledgeBaseWithContent>(
        `/v1/knowledge-bases/${knowledgeBaseUuid}`,
        {
            signal,
        }
    );
    return response.data;
}

export async function createKnowledgeBase(
    data: KnowledgeBaseCreateRequest,
    signal?: AbortSignal
): Promise<KnowledgeBaseSchema> {
    const response = await apiClient.post<KnowledgeBaseSchema>('/v1/knowledge-bases/', data, {
        signal,
    });
    return response.data;
}

export async function updateKnowledgeBase(
    knowledgeBaseUuid: string,
    data: KnowledgeBaseUpdateRequest,
    signal?: AbortSignal
): Promise<KnowledgeBaseSchema> {
    const response = await apiClient.put<KnowledgeBaseSchema>(
        `/v1/knowledge-bases/${knowledgeBaseUuid}`,
        data,
        {
            signal,
        }
    );
    return response.data;
}

export async function deleteKnowledgeBase(
    knowledgeBaseUuid: string,
    signal?: AbortSignal
): Promise<void> {
    await apiClient.delete(`/v1/knowledge-bases/${knowledgeBaseUuid}`, { signal });
}

// File API functions
export async function listFiles(
    knowledgeBaseUuid?: string,
    signal?: AbortSignal
): Promise<FileSchema[]> {
    const url = knowledgeBaseUuid
        ? `/v1/files/?knowledge_base_uuid=${knowledgeBaseUuid}`
        : '/v1/files/';
    const response = await apiClient.get<{ files: FileSchema[] }>(url, { signal });
    return response.data.files;
}

export async function getFile(
    fileUuid: string,
    includeContent: boolean = false,
    signal?: AbortSignal
): Promise<FileSchema> {
    const url = `/v1/files/${fileUuid}?include_content=${includeContent}`;
    const response = await apiClient.get<FileSchema>(url, { signal });
    return response.data;
}

export async function updateFile(
    fileUuid: string,
    data: { filename?: string; knowledge_base_uuid?: string },
    signal?: AbortSignal
): Promise<FileSchema> {
    const response = await apiClient.put<FileSchema>(`/v1/files/${fileUuid}`, data, { signal });
    return response.data;
}

export async function deleteFile(fileUuid: string, signal?: AbortSignal): Promise<void> {
    await apiClient.delete(`/v1/files/${fileUuid}`, { signal });
}

export async function uploadFiles({
    onUploadProgress,
    files,
    signal,
    knowledgeBaseUuid: knowledgeBaseUuid,
}: {
    files?: File[];
    onUploadProgress?: (progressEvent: AxiosProgressEvent) => void;
    signal?: AbortSignal;
    knowledgeBaseUuid?: string;
}) {
    const formData = new FormData();

    if (files && files.length > 0) {
        files.forEach(file => formData.append('files', file));
    }

    const uploadUrl = knowledgeBaseUuid
        ? `/v1/files/local/upload?knowledge_base_uuid=${knowledgeBaseUuid}`
        : '/v1/files/local/upload';
    const uploadResponse = await apiClient.post(uploadUrl, formData, {
        headers: {
            'content-type': 'multipart/form-data',
        },
        onUploadProgress,
        signal,
    });

    const uploadedFiles: FileSchema[] = uploadResponse.data;

    // Only fetch content if knowledgeBaseUuid is provided
    if (!knowledgeBaseUuid) {
        return uploadedFiles;
    }

    // File is uploaded, grab the metadata for each with content
    const filesWithContent: FileSchema[] = [];

    for (const file of uploadedFiles) {
        try {
            const fileWithContent = await getFile(file.uuid, true, signal);
            filesWithContent.push(fileWithContent);
        } catch (error) {
            // If getting content fails, include the file without content
            console.warn(`Failed to get content for file ${file.filename}:`, error);
            filesWithContent.push({
                ...file,
                encoded_content: {},
            });
        }
    }

    return filesWithContent;
}
