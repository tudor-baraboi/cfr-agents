/**
 * WebSocket message types from the backend
 */
export interface TextEvent {
  type: 'text';
  content: string;
}

export interface ThinkingEvent {
  type: 'thinking';
  content: string;
}

export interface ToolUseEvent {
  type: 'tool_use';
  name: string;
  id: string;
}

export interface ToolInputEvent {
  type: 'tool_input';
  partial: string;
}

export interface ToolExecutingEvent {
  type: 'tool_executing';
  tool: string;
  input: Record<string, unknown>;
}

export interface ToolResultEvent {
  type: 'tool_result';
  tool: string;
  result: string;
}

export interface ErrorEvent {
  type: 'error';
  content: string;
}

export interface WarningEvent {
  type: 'warning';
  content: string;
}

export interface ClearTextEvent {
  type: 'clear_text';
  chars: number;
}

export interface DoneEvent {
  type: 'done';
}

export interface PingEvent {
  type: 'ping';
}

export interface QuotaUpdateEvent {
  type: 'quota_update';
  requests_used: number;
  requests_remaining: number;
  daily_limit: number;
}

export type WebSocketEvent =
  | TextEvent
  | ThinkingEvent
  | ToolUseEvent
  | ToolInputEvent
  | ToolExecutingEvent
  | ToolResultEvent
  | ErrorEvent
  | WarningEvent
  | ClearTextEvent
  | DoneEvent
  | PingEvent
  | QuotaUpdateEvent;

/**
 * Application message types
 */
export interface ToolCall {
  name: string;
  status: 'pending' | 'executing' | 'done';
  input?: Record<string, unknown>;
  result?: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  thinking?: string;  // Extended Thinking: Claude's reasoning process
  toolCalls?: ToolCall[];
  citations?: string[];
  timestamp: Date;
  isStreaming?: boolean;
  isWarning?: boolean;  // Context limit warning
}

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected';

/**
 * Authentication types
 */
export interface AuthState {
  token: string | null;
  isAdmin: boolean;
  requestsUsed: number;
  requestsRemaining: number;
  dailyLimit: number;
  fingerprint?: string;
}

export interface ValidateCodeResponse {
  token: string;
  is_admin: boolean;
  requests_used: number;
  requests_remaining: number | null;
}

export interface FingerprintResponse {
  token: string;
  is_admin: boolean;
  requests_used: number;
  requests_remaining: number;
  daily_limit: number;
}

/**
 * Quota exhaustion state
 */
export interface QuotaExhaustedState {
  exhausted: boolean;
  message: string;
}
