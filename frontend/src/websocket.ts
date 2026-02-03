import { createSignal } from 'solid-js';
import type { ConnectionStatus, WebSocketEvent, QuotaUpdateEvent } from './types';
import { AGENT } from './config';
import { logger } from './logger';

export type EventHandler = (event: WebSocketEvent) => void;
export type TrialExhaustedHandler = (message: string) => void;
export type QuotaUpdateHandler = (used: number, remaining: number) => void;
export type AuthFailedHandler = () => void;

// Backend API URL - use environment variable or default to same origin
const API_URL = import.meta.env.VITE_API_URL || '';

// Auth-related close codes that should NOT trigger reconnect
const AUTH_CLOSE_CODES = [4001, 4003]; // 4001 = auth required/invalid, 4003 = trial exhausted

/**
 * Creates a WebSocket connection manager with auto-reconnect
 */
export function createWebSocket(conversationId: string, token: string) {
  const [status, setStatus] = createSignal<ConnectionStatus>('disconnected');
  let ws: WebSocket | null = null;
  let eventHandler: EventHandler | null = null;
  let trialExhaustedHandler: TrialExhaustedHandler | null = null;
  let quotaUpdateHandler: QuotaUpdateHandler | null = null;
  let reconnectTimer: number | null = null;
  let reconnectAttempts = 0;
  const maxReconnectAttempts = 5;
  const baseReconnectDelay = 1000;
  let authFailedHandler: AuthFailedHandler | null = null;

  function getWebSocketUrl(): string {
    if (API_URL) {
      // Use configured API URL
      const url = new URL(API_URL);
      const protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
      return `${protocol}//${url.host}/ws/chat/${conversationId}?token=${encodeURIComponent(token)}&agent=${AGENT}`;
    }
    // Fall back to same origin (for local development)
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    return `${protocol}//${host}/ws/chat/${conversationId}?token=${encodeURIComponent(token)}&agent=${AGENT}`;
  }

  function connect() {
    if (ws?.readyState === WebSocket.OPEN || ws?.readyState === WebSocket.CONNECTING) {
      return;
    }

    setStatus('connecting');
    const url = getWebSocketUrl();
    
    try {
      ws = new WebSocket(url);

      ws.onopen = () => {
        setStatus('connected');
        reconnectAttempts = 0;
        logger.info('ws', 'WebSocket connected');
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as WebSocketEvent;
          // Ignore ping messages (keep-alive)
          if (data.type === 'ping') {
            return;
          }
          // Handle quota updates specially
          if (data.type === 'quota_update') {
            const quotaData = data as QuotaUpdateEvent;
            logger.info('ws', 'Quota update', { used: quotaData.requests_used, remaining: quotaData.requests_remaining });
            quotaUpdateHandler?.(quotaData.requests_used, quotaData.requests_remaining);
            return;
          }
          logger.info('ws', `Message: ${data.type}`, data.type === 'text' ? { preview: data.content.slice(0, 100) } : undefined);
          eventHandler?.(data);
        } catch (error) {
          logger.error('ws', 'Failed to parse WebSocket message', { error, raw: event.data.slice(0, 200) });
        }
      };

      ws.onclose = (event) => {
        setStatus('disconnected');
        logger.info('ws', 'WebSocket closed', { code: event.code, reason: event.reason, wasClean: event.wasClean });
        
        // Check if this is a trial exhausted close
        if (event.code === 4003) {
          logger.warn('ws', 'Quota exhausted - notifying handler');
          trialExhaustedHandler?.(event.reason || "You've used your daily queries. Come back tomorrow!");
          return; // Don't reconnect
        }
        
        // Don't reconnect on auth-related close codes - trigger re-auth instead
        if (AUTH_CLOSE_CODES.includes(event.code)) {
          logger.warn('ws', 'Auth-related close - triggering re-auth', { code: event.code });
          authFailedHandler?.();
          return;
        }
        
        // Auto-reconnect unless intentionally closed (code 1000)
        // Also reconnect on abnormal closures (code 1006) which happen on mobile/network issues
        if (event.code !== 1000 && reconnectAttempts < maxReconnectAttempts) {
          scheduleReconnect();
        }
      };

      ws.onerror = (error) => {
        logger.error('ws', 'WebSocket error', { error });
      };
    } catch (error) {
      logger.error('ws', 'Failed to create WebSocket', { error });
      setStatus('disconnected');
      scheduleReconnect();
    }
  }

  function scheduleReconnect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
    }
    
    // Faster reconnection with shorter delays
    const delay = Math.min(baseReconnectDelay * Math.pow(1.5, reconnectAttempts), 10000);
    reconnectAttempts++;
    
    logger.info('ws', `Reconnecting in ${delay}ms (attempt ${reconnectAttempts})`);
    reconnectTimer = window.setTimeout(connect, delay);
  }

  function disconnect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    
    if (ws) {
      ws.close(1000, 'Client disconnected');
      ws = null;
    }
    
    setStatus('disconnected');
  }

  function send(message: string) {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ message }));
      return true;
    }
    logger.warn('ws', 'WebSocket not connected - cannot send message');
    return false;
  }

  function onEvent(handler: EventHandler) {
    eventHandler = handler;
  }

  function onTrialExhausted(handler: TrialExhaustedHandler) {
    trialExhaustedHandler = handler;
  }

  function onQuotaUpdate(handler: QuotaUpdateHandler) {
    quotaUpdateHandler = handler;
  }

  function onAuthFailed(handler: AuthFailedHandler) {
    authFailedHandler = handler;
  }

  return {
    status,
    connect,
    disconnect,
    send,
    onEvent,
    onTrialExhausted,
    onQuotaUpdate,
    onAuthFailed,
  };
}
