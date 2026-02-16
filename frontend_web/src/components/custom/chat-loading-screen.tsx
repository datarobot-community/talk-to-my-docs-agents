import { Skeleton } from '@/components/ui/skeleton';

const ChatLoadingScreen = () => {
    return (
        <div className="flex min-h-[calc(100vh-4rem)] w-full flex-1 flex-col space-y-4 p-4">
            <div className="flex items-center space-x-4">
                <Skeleton className="size-[36px] rounded-[100px]" />
                <Skeleton className="h-6 w-1/7" />
            </div>
            <Skeleton className="mb-9 h-6 w-2/3" />
            <div className="flex items-center space-x-4">
                <Skeleton className="size-[36px] rounded-[100px]" />
                <Skeleton className="h-6 w-1/6" />
            </div>
            <Skeleton className="h-6 w-full" />
            <Skeleton className="h-6 w-5/6" />
            <Skeleton className="h-6 w-1/2" />
            <div className="flex flex-1 flex-col"></div>
            <Skeleton className="h-18 w-full" />
        </div>
    );
};

export { ChatLoadingScreen };
