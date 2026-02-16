import React, { PropsWithChildren, HTMLAttributes } from 'react';
import { cn, extractText, isSuggestedPrompt } from '@/lib/utils';
import { SquareArrowOutUpRight } from 'lucide-react';
import { InteractiveSuggestion } from '../components/custom/interactive-suggestion';
import { Heading } from '@/components/ui/heading';

type MarkdownComponentProps = PropsWithChildren<HTMLAttributes<HTMLElement>>;

export const MARKDOWN_COMPONENTS = {
    ul: ({ children, ...props }: MarkdownComponentProps) => {
        // Check if any li children contain suggestion content
        const hasSuggestion = React.Children.toArray(children).some(child => {
            if (
                React.isValidElement(child) &&
                child.props &&
                typeof child.props === 'object' &&
                'children' in child.props
            ) {
                const childProps = child.props as { children: React.ReactNode };
                // Check if this li element contains suggestion content
                return React.Children.toArray(childProps.children).some(isSuggestedPrompt);
            }
            return false;
        });

        return (
            <ul
                className={cn('my-4 leading-relaxed', hasSuggestion ? 'pl-0' : 'list-disc pl-8')}
                {...props}
            >
                {children}
            </ul>
        );
    },
    ol: ({ children, ...props }: MarkdownComponentProps) => (
        <ol className="my-4 list-decimal pl-8 leading-relaxed" {...props}>
            {children}
        </ol>
    ),
    li: ({ children, ...props }: MarkdownComponentProps) => {
        let childrenText = '';
        let isSuggestion = false;
        let questionText = '';

        // Check if this list item contains a suggestion
        if (Array.isArray(children)) {
            isSuggestion = children.some(isSuggestedPrompt);
            childrenText = extractText(children);
        } else if (children) {
            // Handle single child case
            isSuggestion = isSuggestedPrompt(children);
            childrenText = extractText([children]);
        }

        // Also check if the text content contains "SUGGESTION:" as a fallback
        if (!isSuggestion && childrenText.includes('SUGGESTION:')) {
            isSuggestion = true;
        }

        if (isSuggestion) {
            // Remove various forms of SUGGESTION: markers including markdown formatting
            questionText = childrenText
                .replace(/^\*\*SUGGESTION:\*\*\s*/, '') // **SUGGESTION:**
                .replace(/^\*SUGGESTION:\*\s*/, '') // *SUGGESTION:*
                .replace(/^SUGGESTION:\s*/, '') // SUGGESTION:
                .trim();

            return (
                <li className="my-1 wrap-break-word" {...props}>
                    <InteractiveSuggestion question={questionText} />
                </li>
            );
        }

        return (
            <li className="my-1" {...props}>
                {children}
            </li>
        );
    },
    h1: ({ children, ...props }: MarkdownComponentProps) => (
        <Heading level={1} className="mt-6 mb-4" {...props}>
            {children}
        </Heading>
    ),
    h2: ({ children, ...props }: MarkdownComponentProps) => (
        <Heading level={2} className="mt-6 mb-4" {...props}>
            {children}
        </Heading>
    ),
    h3: ({ children, ...props }: MarkdownComponentProps) => (
        <Heading level={3} className="mt-4 mb-2" {...props}>
            {children}
        </Heading>
    ),
    p: ({ children, ...props }: MarkdownComponentProps) => (
        <p className="body leading-relaxed" {...props}>
            {children}
        </p>
    ),
    hr: ({ ...props }: MarkdownComponentProps) => <hr className="mt-4 mb-2" {...props} />,
    th: ({ children, className, ...props }: MarkdownComponentProps) => (
        <th className={cn('px-3 py-2 text-left', className)} {...props}>
            {children}
        </th>
    ),
    td: ({ children, className, ...props }: MarkdownComponentProps) => (
        <td className={cn('px-3 py-2', className)} {...props}>
            {children}
        </td>
    ),
    a: ({ children, ...props }: MarkdownComponentProps) => (
        <a target="_blank" className="inline-flex items-center anchor" {...props}>
            {children}
            <SquareArrowOutUpRight size={18} className="ml-1" />
        </a>
    ),
};
