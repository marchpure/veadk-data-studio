export type LLMProvider = 'openai' | 'anthropic' | 'claude_code' | 'codex' | 'openrouter' | 'azure' | 'bedrock' | 'groq' | 'xai'

export interface LLMConnection {
  id: string
  type: LLMProvider
  name?: string
  config: Record<string, any>
  created_at: string
}

export interface LLMConnectionCreateRequest {
  type: LLMProvider
  name?: string
  config: Record<string, any>
}

export interface LLMConnectionListResponse {
  items: LLMConnection[]
  total?: number
}

// Provider-specific configuration interfaces
export interface OpenAIConfig {
  api_key: string
}

export interface AnthropicConfig {
  api_key: string
}

export type ClaudeCodeConfig = Record<string, never>

export interface OpenRouterConfig {
  api_key: string
}

export interface AzureConfig {
  api_key: string
  api_base: string
  api_version: string
  models?: string
}

export interface BedrockConfig {
  aws_access_key_id: string
  aws_secret_access_key: string
  aws_region_name: string
  models?: string
}

export interface GroqConfig {
  api_key: string
}

export interface CodexConfig {
  access_token?: string
  refresh_token?: string
  expires_at?: number
}

// Provider metadata for dynamic forms
export interface ProviderField {
  name: string
  label: string
  type: 'text' | 'password' | 'url' | 'select' | 'checkbox'
  required: boolean
  placeholder?: string
  description?: string
  options?: { value: string; label: string }[]
  defaultValue?: string | boolean
}

export interface ProviderMetadata {
  name: string
  displayName: string
  description: string
  fields: ProviderField[]
}

// Provider configurations
export const PROVIDER_CONFIGS: Record<LLMProvider, ProviderMetadata> = {
  openai: {
    name: 'openai',
    displayName: 'OpenAI',
    description: '',
    fields: [
      {
        name: 'api_key',
        label: 'API Key',
        type: 'password',
        required: true,
        placeholder: 'sk-...'
      }
    ]
  },
  anthropic: {
    name: 'anthropic',
    displayName: 'Anthropic',
    description: '',
    fields: [
      {
        name: 'api_key',
        label: 'API Key',
        type: 'password',
        required: true,
        placeholder: 'sk-ant-...'
      }
    ]
  },
  claude_code: {
    name: 'claude_code',
    displayName: 'Claude Code',
    description: 'Use Claude models via Claude Code authentication (no API key required)',
    fields: [
      {
        name: 'use_claude_code_auth',
        label: 'I have authenticated with Claude Code',
        type: 'checkbox',
        required: true,
        description: 'Confirm that you have logged into Claude Code in terminal already',
        defaultValue: true
      }
    ]
  },
  codex: {
    name: 'codex',
    displayName: 'OpenAI Codex',
    description: 'Use Codex models via your ChatGPT Plus/Pro subscription (no API credits needed)',
    fields: []
  },
  openrouter: {
    name: 'openrouter',
    displayName: 'OpenRouter',
    description: '',
    fields: [
      {
        name: 'api_key',
        label: 'API Key',
        type: 'password',
        required: true,
        placeholder: 'sk-or-...'
      }
    ]
  },
  azure: {
    name: 'azure',
    displayName: 'Azure',
    description: '',
    fields: [
      {
        name: 'api_key',
        label: 'API Key',
        type: 'password',
        required: true,
        placeholder: 'your-azure-api-key'
      },
      {
        name: 'api_base',
        label: 'API Base URL',
        type: 'url',
        required: true,
        placeholder: 'https://your-resource.openai.azure.com/'
      },
      {
        name: 'api_version',
        label: 'API Version',
        type: 'text',
        required: true,
        placeholder: '2024-10-21',
        defaultValue: '2024-10-21'
      },
      {
        name: 'models',
        label: 'Deployment Name(s)',
        type: 'text',
        required: true,
        placeholder: 'my-gpt4-deployment',
        description: 'Deployment name or comma-separated names'
      }
    ]
  },
  bedrock: {
    name: 'bedrock',
    displayName: 'AWS Bedrock',
    description: '',
    fields: [
      {
        name: 'aws_access_key_id',
        label: 'AWS Access Key ID',
        type: 'password',
        required: true,
        placeholder: 'AKIA...'
      },
      {
        name: 'aws_secret_access_key',
        label: 'AWS Secret Access Key',
        type: 'password',
        required: true,
        placeholder: 'your-secret-key'
      },
      {
        name: 'aws_region_name',
        label: 'AWS Region',
        type: 'text',
        required: true,
        placeholder: 'us-east-1',
        defaultValue: 'us-east-1'
      },
      {
        name: 'models',
        label: 'Model ID(s)',
        type: 'text',
        required: true,
        placeholder: 'bedrock/anthropic.claude-3-sonnet-20240229-v1:0',
        description: 'Bedrock model ID or comma-separated IDs'
      }
    ]
  },
  groq: {
    name: 'groq',
    displayName: 'Groq',
    description: '',
    fields: [
      {
        name: 'api_key',
        label: 'API Key',
        type: 'password',
        required: true,
        placeholder: 'gsk_...'
      }
    ]
  },
  xai: {
    name: 'xai',
    displayName: 'Grok',
    description: '',
    fields: [
      {
        name: 'api_key',
        label: 'API Key',
        type: 'password',
        required: true,
        placeholder: 'xai-...'
      }
    ]
  }
}
