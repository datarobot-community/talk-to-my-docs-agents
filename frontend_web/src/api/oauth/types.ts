export interface IOAuthProvider {
    id: string;
    name: string;
    status?: string | null;
    type?: string;
    client_id?: string | null;
    metadata?: Record<string, unknown> | null;
}

export interface IOAuthProviderListResponse {
    providers: IOAuthProvider[];
}

export interface IOAuthAuthorizeResponse {
    redirect_url: string;
}
