export const DotPulseLoader = () => {
    return (
        <div className="flex items-center space-x-1 ">
            <span
                className="w-2 h-2 bg-gray-500 rounded-full animate-bounce"
                style={{ animationDelay: '0ms' }}
            />
            <span
                className="w-2 h-2 bg-gray-500 rounded-full animate-bounce"
                style={{ animationDelay: '100ms' }}
            />
            <span
                className="w-2 h-2 bg-gray-500 rounded-full animate-bounce"
                style={{ animationDelay: '200ms' }}
            />
        </div>
    );
};
