import apiClient from '../apiClient';
import { ExternalFilesResponse, SharePointNavState } from './types';
import { FileSchema } from '../knowledge-bases/types';

export async function getGoogleFiles(folderId?: string) {
    const url = folderId
        ? `/v1/docs/google/files/?folder_id=${folderId}`
        : '/v1/docs/google/files/';

    const response = await apiClient.get<ExternalFilesResponse>(url);
    console.log('Google API response:', response.data);
    return response.data;
}

export async function getBoxFiles(folderId: string = '0') {
    const response = await apiClient.get<ExternalFilesResponse>(
        `/v1/docs/box/files/?folder_id=${folderId}`
    );
    console.log('Box API response:', response.data);
    return response.data;
}

export async function getSharePointFiles(nav: SharePointNavState = {}) {
    const params = new URLSearchParams();
    if (nav.siteId) params.append('site_id', nav.siteId);
    if (nav.driveId) params.append('drive_id', nav.driveId);
    if (nav.folderId) params.append('folder_id', nav.folderId);

    const queryString = params.toString();
    const url = queryString
        ? `/v1/docs/sharepoint/files/?${queryString}`
        : '/v1/docs/sharepoint/files/';

    const response = await apiClient.get<ExternalFilesResponse>(url);
    console.log('SharePoint API response:', response.data);
    return response.data;
}

export async function uploadGoogleFile({
    fileId,
    knowledgeBaseUuid: knowledgeBaseUuid,
    signal,
}: {
    fileId: string;
    knowledgeBaseUuid?: string;
    signal?: AbortSignal;
}): Promise<FileSchema[]> {
    const uploadUrl = knowledgeBaseUuid
        ? `/v1/files/drive/upload?knowledge_base_uuid=${knowledgeBaseUuid}`
        : '/v1/files/drive/upload';

    const uploadResponse = await apiClient.post(
        uploadUrl,
        { file_ids: [fileId] }, // Send as object with file_ids array
        {
            headers: {
                'content-type': 'application/json',
            },
            signal,
        }
    );

    const uploadedFiles: FileSchema[] = Array.isArray(uploadResponse.data)
        ? uploadResponse.data
        : [uploadResponse.data];

    const filesWithContent: FileSchema[] = [];

    for (const file of uploadedFiles) {
        try {
            const contentResponse = await apiClient.get(`/v1/files/${file.uuid}`, { signal });

            const fileWithContent: FileSchema = {
                ...contentResponse.data,
                encoded_content: contentResponse.data.encoded_content || {},
            };

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

export async function uploadBoxFile({
    fileId,
    knowledgeBaseUuid: knowledgeBaseUuid,
    signal,
}: {
    fileId: string;
    knowledgeBaseUuid?: string;
    signal?: AbortSignal;
}): Promise<FileSchema[]> {
    // Step 1: Upload the Box file
    const uploadUrl = knowledgeBaseUuid
        ? `/v1/files/box/upload?knowledge_base_uuid=${knowledgeBaseUuid}`
        : '/v1/files/box/upload';

    const uploadResponse = await apiClient.post(
        uploadUrl,
        { file_ids: [fileId] }, // Send as object with file_ids array
        {
            headers: {
                'content-type': 'application/json',
            },
            signal,
        }
    );

    const uploadedFiles: FileSchema[] = Array.isArray(uploadResponse.data)
        ? uploadResponse.data
        : [uploadResponse.data];

    // Step 2: Get encoded content for each uploaded file
    const filesWithContent: FileSchema[] = [];

    for (const file of uploadedFiles) {
        try {
            const contentResponse = await apiClient.get(`/v1/files/${file.uuid}`, { signal });

            const fileWithContent: FileSchema = {
                ...contentResponse.data,
                encoded_content: contentResponse.data.encoded_content || {},
            };

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

export async function uploadSharePointFile({
    fileId,
    knowledgeBaseUuid: knowledgeBaseUuid,
    signal,
}: {
    fileId: string;
    knowledgeBaseUuid?: string;
    signal?: AbortSignal;
}): Promise<FileSchema[]> {
    const uploadUrl = knowledgeBaseUuid
        ? `/v1/files/sharepoint/upload?knowledge_base_uuid=${knowledgeBaseUuid}`
        : '/v1/files/sharepoint/upload';

    const uploadResponse = await apiClient.post(
        uploadUrl,
        { file_ids: [fileId] },
        {
            headers: {
                'content-type': 'application/json',
            },
            signal,
        }
    );

    const uploadedFiles: FileSchema[] = Array.isArray(uploadResponse.data)
        ? uploadResponse.data
        : [uploadResponse.data];

    const filesWithContent: FileSchema[] = [];

    for (const file of uploadedFiles) {
        try {
            const contentResponse = await apiClient.get(`/v1/files/${file.uuid}`, { signal });

            const fileWithContent: FileSchema = {
                ...contentResponse.data,
                encoded_content: contentResponse.data.encoded_content || {},
            };

            filesWithContent.push(fileWithContent);
        } catch (error) {
            console.warn(`Failed to get content for file ${file.filename}:`, error);
            filesWithContent.push({
                ...file,
                encoded_content: {},
            });
        }
    }

    return filesWithContent;
}
