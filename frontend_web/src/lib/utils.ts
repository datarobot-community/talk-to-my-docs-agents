import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { VITE_STATIC_DEFAULT_PORT, VITE_DEFAULT_PORT } from '@/constants/dev';
import { IChat } from '@/api/chat/types.ts';

export function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

export function getApiPort() {
    return window.ENV?.API_PORT || VITE_STATIC_DEFAULT_PORT;
}

export function getBaseUrl() {
    let basename = window.ENV?.BASE_PATH;
    // Adjust API URL based on the environment
    const pathname: string = window.location.pathname;

    if (pathname?.includes('notebook-sessions') && pathname?.includes(`/${VITE_DEFAULT_PORT}/`)) {
        // ex:. /notebook-sessions/{id}/ports/5137/
        basename = import.meta.env.BASE_URL;
    }

    return basename ? basename : '/';
}

export function getApiUrl() {
    return `${window.location.origin}${getBaseUrl()}api`;
}

export function unwrapMarkdownCodeBlock(message: string): string {
    return message.replace(/```(?:markdown)?\s*/g, '\n').replace(/<think>[\s\S]*?<\/think>/g, '');
}

const DEFAULT_CHAT_NAME = 'New Chat';
export const getChatNameOrDefaultWithTimestamp = (chat: IChat) => {
    const chatName = chat.name || DEFAULT_CHAT_NAME;
    if (chatName === DEFAULT_CHAT_NAME) {
        const date = chat.created_at
            ? new Date(
                  chat.created_at.endsWith('Z') || chat.created_at.endsWith('+00:00')
                      ? chat.created_at
                      : chat.created_at + 'Z'
              )
            : new Date();
        const formattedDate = new Intl.DateTimeFormat('en', {
            month: 'long',
            day: 'numeric',
        }).format(date);
        const formattedTime = new Intl.DateTimeFormat('en', {
            hour: 'numeric',
            minute: '2-digit',
            hour12: true,
        }).format(date);
        return `Chat ${formattedDate} ${formattedTime}`;
    }
    return chatName;
};

export function formatFileSize(bytes: number): string {
    if (bytes >= 1024 * 1024) {
        return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
    } else if (bytes >= 1024) {
        return (bytes / 1024).toFixed(0) + ' KB';
    } else {
        return bytes + ' bytes';
    }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const extractText = (element: any): string => {
    if (typeof element === 'string') return element;
    if (Array.isArray(element)) return element.map(extractText).join('');
    if (element && typeof element === 'object' && element.props) {
        return extractText(element.props.children);
    }
    return '';
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const isSuggestedPrompt = (element: any): boolean => {
    if (element && typeof element === 'object' && element.type === 'strong') {
        const strongText = extractText(element.props.children);
        return strongText === 'SUGGESTION:';
    }

    // Also check if the element itself contains "SUGGESTION:" text
    if (element && typeof element === 'string') {
        return element.includes('SUGGESTION:');
    }

    // Check if it's a React element with children that contain "SUGGESTION:"
    if (element && typeof element === 'object' && element.props && element.props.children) {
        const text = extractText(element.props.children);
        return text.includes('SUGGESTION:');
    }

    return false;
};
