export interface FileSchema {
    uuid: string;
    filename: string;
    source: string;
    file_path?: string | null;
    external_id?: string | null;
    mime_type?: string | null;
    size_bytes?: number | null;
    added: string;
    knowledge_base_id?: number | null;
    owner_uuid: string;
    encoded_content?: Record<string, string> | null;
}

export interface KnowledgeBaseFileSchema {
    uuid: string;
    filename: string;
    source: string;
    added: string;
    owner_uuid: string;
}

export interface KnowledgeBaseSchema {
    uuid: string;
    title: string;
    description: string;
    token_count: number;
    path: string;
    created_at: string;
    updated_at: string;
    owner_uuid: string;
    files: KnowledgeBaseFileSchema[];
}

export interface KnowledgeBaseWithContent extends KnowledgeBaseSchema {
    encoded_content?: Record<string, string>;
}

export interface KnowledgeBaseCreateRequest {
    title: string;
    description: string;
    path?: string;
    token_count?: number;
}

export interface KnowledgeBaseUpdateRequest {
    title?: string;
    description?: string;
    path?: string;
}

export interface KnowledgeBaseListResponse {
    knowledge_bases: KnowledgeBaseSchema[];
}
