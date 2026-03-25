export interface ExternalFile {
    id: string;
    type: 'folder' | 'file' | 'web_link';
    name: string;
    mime_type?: string | null;
}

export interface ExternalFilesResponse {
    files: ExternalFile[];
}

export interface ConnectedSource {
    id: string;
    name: string;
    type: 'google' | 'box' | 'sharepoint';
    isConnected: boolean;
}

// SharePoint navigation state for file IDs
export interface SharePointNavState {
    siteId?: string;
    driveId?: string;
    folderId?: string;
}
