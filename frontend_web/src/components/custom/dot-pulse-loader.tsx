export const DotPulseLoader = () => {
    return (
        <div className="flex items-center space-x-1">
            <span
                className="size-2 animate-bounce rounded-full bg-muted-foreground"
                style={{ animationDelay: '0ms' }}
            />
            <span
                className="size-2 animate-bounce rounded-full bg-muted-foreground"
                style={{ animationDelay: '100ms' }}
            />
            <span
                className="size-2 animate-bounce rounded-full bg-muted-foreground"
                style={{ animationDelay: '200ms' }}
            />
        </div>
    );
};
