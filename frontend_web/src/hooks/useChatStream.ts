import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { getApiUrl } from '@/lib/utils';
import { chatKeys } from '@/api/chat/keys';
import { IChatMessage } from '@/api/chat/types';

const MAX_CONSECUTIVE_FAILURES = 3;
const POLLING_BACKOFF_MS = 30000;

enum StreamEventType {
    SNAPSHOT = 'snapshot',
    MESSAGE = 'message',
    HEARTBEAT = 'heartbeat',
    TASK_PROGRESS = 'task_progress',
}

interface TaskProgressData {
    type: 'task_started' | 'task_completed';
    task_name: string;
    agent_name: string;
}

type StreamEvent =
    | { type: StreamEventType.SNAPSHOT; data: IChatMessage[] }
    | { type: StreamEventType.MESSAGE; data: IChatMessage }
    | { type: StreamEventType.HEARTBEAT; timestamp: string }
    | { type: StreamEventType.TASK_PROGRESS; data: TaskProgressData }
    | { type: string; data?: unknown };

export const useChatStream = (chatId?: string) => {
    const queryClient = useQueryClient();
    // Flag toggled when we abandon SSE temporarily and reintroduce polling.
    const [isPollingFallbackActive, setIsPollingFallbackActive] = useState(false);
    // Remember the timer so we can retry SSE after a cooling-off window.
    const retryTimeoutRef = useRef<number | undefined>(undefined);
    // Count consecutive SSE failures for this chat (reset once SSE reconnects).
    const failureCountRef = useRef(0);

    // When the user opens a different chat we reset retry state and clear timers.
    useEffect(() => {
        failureCountRef.current = 0;
        setIsPollingFallbackActive(false);
        if (retryTimeoutRef.current) {
            window.clearTimeout(retryTimeoutRef.current);
            retryTimeoutRef.current = undefined;
        }
    }, [chatId]);

    // Clear retry timers on unmount.
    useEffect(() => {
        return () => {
            if (retryTimeoutRef.current) {
                window.clearTimeout(retryTimeoutRef.current);
                retryTimeoutRef.current = undefined;
            }
        };
    }, []);

    // Resets the failure count and disables polling fallback when the
    // browser detects network is back, triggering SSE reconnection.
    useEffect(() => {
        const handleOnline = () => {
            failureCountRef.current = 0;
            setIsPollingFallbackActive(false);
        };
        window.addEventListener('online', handleOnline);
        return () => window.removeEventListener('online', handleOnline);
    }, []);

    // Spin up an SSE stream per chat; if it keeps failing we switch to polling.
    useEffect(() => {
        const baseApiUrl = getApiUrl();
        if (!chatId || isPollingFallbackActive) {
            return;
        }

        const eventSource = new EventSource(`${baseApiUrl}/v1/chat/${chatId}/messages-stream`, {
            withCredentials: true,
        });

        eventSource.onopen = () => {
            failureCountRef.current = 0;
            setIsPollingFallbackActive(false);
        };

        eventSource.onerror = () => {
            failureCountRef.current += 1;
            console.debug('Chat SSE disconnected, attempt', failureCountRef.current);
            if (failureCountRef.current >= MAX_CONSECUTIVE_FAILURES) {
                // After MAX_CONSECUTIVE_FAILURES failed reconnects we temporarily fall back to polling.
                setIsPollingFallbackActive(true);
                eventSource.close();
                if (!retryTimeoutRef.current) {
                    retryTimeoutRef.current = window.setTimeout(() => {
                        retryTimeoutRef.current = undefined;
                        failureCountRef.current = 0;
                        setIsPollingFallbackActive(false);
                    }, POLLING_BACKOFF_MS);
                }
            }
        };

        eventSource.onmessage = event => {
            try {
                const streamEvent: StreamEvent = JSON.parse(event.data);

                switch (streamEvent.type) {
                    case StreamEventType.SNAPSHOT:
                        // Replace the cache with the server snapshot so history stays authoritative.
                        if (Array.isArray(streamEvent.data)) {
                            queryClient.setQueryData<IChatMessage[]>(
                                chatKeys.messages(chatId),
                                streamEvent.data as IChatMessage[]
                            );
                        }
                        break;

                    case StreamEventType.MESSAGE:
                        // Merge the incoming message (new entry or an update in place).
                        if (streamEvent.data) {
                            const nextMessage = streamEvent.data as IChatMessage;
                            queryClient.setQueryData<IChatMessage[]>(
                                chatKeys.messages(chatId),
                                (old = []) => {
                                    const existingIndex = old.findIndex(
                                        msg => msg.uuid === nextMessage.uuid
                                    );
                                    if (existingIndex >= 0) {
                                        // Update existing message (e.g., AI response streaming)
                                        const next = [...old];
                                        next[existingIndex] = nextMessage;
                                        return next;
                                    }
                                    // Add new message
                                    return [...old, nextMessage];
                                }
                            );
                        }
                        break;

                    case StreamEventType.HEARTBEAT:
                        // Keep-alive heartbeat - prevents server/proxy timeouts, ~25s intervals (_HEARTBEAT_SECONDS)
                        // No processing needed, just maintains SSE connection
                        break;

                    case StreamEventType.TASK_PROGRESS:
                        // Update the in-progress message's task_outputs
                        if (streamEvent.data) {
                            const taskData = streamEvent.data as TaskProgressData;
                            queryClient.setQueryData<IChatMessage[]>(
                                chatKeys.messages(chatId),
                                (old = []) => {
                                    // Find the in-progress assistant message
                                    const inProgressIdx = old.findIndex(
                                        msg => msg.in_progress && msg.role === 'assistant'
                                    );
                                    if (inProgressIdx < 0) return old;

                                    const next = [...old];
                                    const message = { ...next[inProgressIdx] };
                                    const taskOutputs = [...(message.task_outputs || [])];

                                    if (taskData.type === 'task_started') {
                                        // Add new task with in_progress status
                                        taskOutputs.push({
                                            task_name: taskData.task_name,
                                            agent_name: taskData.agent_name,
                                            status: 'in_progress',
                                        });
                                    } else if (taskData.type === 'task_completed') {
                                        // Find task with matching name and agent, mark complete
                                        const completedTaskName = taskData.task_name;
                                        const completedAgentName = taskData.agent_name;
                                        for (let i = taskOutputs.length - 1; i >= 0; i--) {
                                            if (
                                                taskOutputs[i].task_name === completedTaskName &&
                                                taskOutputs[i].agent_name === completedAgentName
                                            ) {
                                                taskOutputs[i] = {
                                                    ...taskOutputs[i],
                                                    status: 'completed',
                                                };
                                                break;
                                            }
                                        }
                                    }

                                    message.task_outputs = taskOutputs;
                                    next[inProgressIdx] = message;
                                    return next;
                                }
                            );
                        }
                        break;

                    default:
                        console.warn('Unknown chat stream event type', streamEvent);
                        break;
                }
            } catch (error) {
                console.error('Failed to process chat stream event', error);
            }
        };

        return () => {
            eventSource.close();
        };
    }, [chatId, queryClient, isPollingFallbackActive]);

    return { isPollingFallbackActive };
};
