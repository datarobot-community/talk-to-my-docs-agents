export const externalFilesKeys = {
    all: ['external-files'] as const,
    google: () => [...externalFilesKeys.all, 'google'] as const,
    googleFolder: (folderId?: string) => [...externalFilesKeys.google(), folderId] as const,
    box: () => [...externalFilesKeys.all, 'box'] as const,
    boxFolder: (folderId: string) => [...externalFilesKeys.box(), folderId] as const,
    sharepoint: () => [...externalFilesKeys.all, 'sharepoint'] as const,
    sharepointFolder: (siteId?: string, driveId?: string, folderId?: string) =>
        [...externalFilesKeys.sharepoint(), siteId, driveId, folderId] as const,
};
