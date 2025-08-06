export const AGENT_MODEL = 'ttmdocs-agents';

export const AGENT_MODEL_LLM = {
    name: '🧠 Intelligent Agent Crew',
    model: AGENT_MODEL,
    llmId: AGENT_MODEL,
    isActive: true,
    isDeprecated: false,
};

export const DEFAULT_LLM_CATALOG = [
    AGENT_MODEL_LLM,
    {
        name: 'Google Gemini 1.5 Flash',
        model: 'vertex_ai/gemini-1.5-flash-002',
        llmId: 'google-gemini-1.5-pro',
        isActive: true,
        isDeprecated: false,
    },
    {
        name: 'Google Gemini 2.0 Flash',
        model: 'vertex_ai/gemini-2.0-flash-001',
        llmId: 'google-gemini-2.0-flash',
        isActive: true,
        isDeprecated: false,
    },
    {
        name: 'Antropic Claude Sonnet 4',
        model: 'bedrock/anthropic.claude-sonnet-4-20250514-v1:0',
        llmId: 'amazon-anthropic-claude-sonnet-4-20250514-v1',
        isActive: true,
        isDeprecated: false,
    },
    {
        name: 'Anthropic Claude 3.5 Sonnet',
        model: 'bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0',
        llmId: 'amazon-anthropic-claude-3.5-sonnet-v2',
        isActive: true,
        isDeprecated: false,
    },
    {
        name: 'Anthropic Claude 3.7 Sonnet',
        model: 'bedrock/anthropic.claude-3-7-sonnet-20250219-v1:0',
        llmId: 'amazon-anthropic-claude-3-7-sonnet-v1',
        isActive: true,
        isDeprecated: false,
    },
    {
        name: 'Azure OpenAI GPT-4o',
        model: 'azure/gpt-4o-2024-11-20',
        llmId: 'azure-openai-gpt-4-o',
        isActive: true,
        isDeprecated: false,
    },
    {
        name: 'Azure OpenAI GPT-4o Mini',
        model: 'azure/gpt-4o-mini',
        llmId: 'azure-openai-gpt-4-o-mini',
        isActive: true,
        isDeprecated: false,
    },
    {
        name: 'DeepSeek R1 v1',
        model: 'bedrock/deepseek.r1-v1:0',
        llmId: 'amazon-deepseek-r1-v1',
        isActive: true,
        isDeprecated: false,
    },
    {
        name: 'Llama 4 Scout',
        model: 'bedrock/meta.llama4-scout-17b-instruct-v1:0',
        llmId: 'amazon-meta-llama-4-scout-17b-instruct-v1',
        isActive: true,
        isDeprecated: false,
    },
];
