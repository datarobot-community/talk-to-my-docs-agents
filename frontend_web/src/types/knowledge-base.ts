export type TFormData = {
    name: string;
    description: string;
    visibility: string;
};

export interface BaseSchema {
    uuid: string;
    title: string;
    description: string;
    token_count: number;
    path: string;
    created_at: string;
    updated_at: string;
    owner_uuid: string;
    files: BaseFileSchema[];
}

export interface BaseFileSchema {
    uuid: string;
    filename: string;
    source: string;
    added: string;
    owner_uuid: string;
}
