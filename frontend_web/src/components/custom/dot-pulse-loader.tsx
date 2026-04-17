export const DotPulseLoader = () => {
    return (
        <div className="flex items-center space-x-1">
            <span
                className="bg-muted-foreground size-2 animate-bounce rounded-full"
                style={{ animationDelay: '0ms' }}
            />
            <span
                className="bg-muted-foreground size-2 animate-bounce rounded-full"
                style={{ animationDelay: '100ms' }}
            />
            <span
                className="bg-muted-foreground size-2 animate-bounce rounded-full"
                style={{ animationDelay: '200ms' }}
            />
        </div>
    );
};
