export interface DRApiResponse<I> {
    totalCount: number;
    count: string;
    next: string | null;
    previous: string | null;
    data: I;
}
