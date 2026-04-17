/// <reference types="vitest/globals" />
import '@testing-library/jest-dom';
import type { SetupServerApi } from 'msw/node';

// Provide a minimal localStorage API before importing modules that rely on it.
if (!globalThis.localStorage || typeof globalThis.localStorage.getItem !== 'function') {
    const store: Record<string, string> = {};
    Object.defineProperty(globalThis, 'localStorage', {
        configurable: true,
        writable: true,
        value: {
            getItem: (key: string) => (key in store ? store[key] : null),
            setItem: (key: string, value: string) => {
                store[key] = String(value);
            },
            removeItem: (key: string) => {
                delete store[key];
            },
            clear: () => {
                for (const key of Object.keys(store)) {
                    delete store[key];
                }
            },
            key: (index: number) => Object.keys(store)[index] ?? null,
            get length() {
                return Object.keys(store).length;
            },
        } as Storage,
    });
}

let server: SetupServerApi | undefined;

beforeAll(async () => {
    const node = await import('./__mocks__/node.js');
    server = node.server;
    server.listen();
});

afterEach(() => {
    server?.resetHandlers();
});

afterAll(() => {
    server?.close();
});

Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
    }),
});

class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
}

global.ResizeObserver = ResizeObserver;

// Mock EventSource for SSE testing with instance tracking
export const eventSourceInstances: EventSourceMock[] = [];

export class EventSourceMock {
    url: string;
    onopen: ((event: Event) => void) | null = null;
    onerror: ((event: Event) => void) | null = null;
    onmessage: ((event: MessageEvent) => void) | null = null;
    readyState = 0;
    CONNECTING = 0;
    OPEN = 1;
    CLOSED = 2;

    constructor(url: string) {
        this.url = url;
        eventSourceInstances.push(this);
    }

    close() {
        this.readyState = 2;
    }

    simulateMessage(data: unknown) {
        if (this.onmessage) {
            this.onmessage(new MessageEvent('message', { data: JSON.stringify(data) }));
        }
    }

    addEventListener() {}
    removeEventListener() {}
    dispatchEvent() {
        return true;
    }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
global.EventSource = EventSourceMock as any;
