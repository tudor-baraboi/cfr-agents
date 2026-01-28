import { createSignal, createEffect, onCleanup, batch } from 'solid-js';
import { createStore, produce } from 'solid-js/store';
import type { Message, ToolCall, WebSocketEvent, ConnectionStatus } from './types';
import { createWebSocket } from './websocket';
import { branding, AGENT } from './config';
import { logger } from './logger';

/**
 * Generates a unique ID for messages
 */
function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

/**
 * Generates a conversation ID (persisted per browser session)
 */
function getConversationId(): string {
  let id = sessionStorage.getItem(`${branding.sessionStoragePrefix}-conversation-id`);
  if (!id) {
    id = `conv-${generateId()}`;
    sessionStorage.setItem(`${branding.sessionStoragePrefix}-conversation-id`, id);
  }
  return id;
}

/**
 * Extracts FAA citations from message content (e.g., §25.1309, AC 20-158)
 */
function extractFaaCitations(content: string): string[] {
  const citations = new Set<string>();
  let match;
  
  // CFR section references: §XX.XXXX or 14 CFR XX.XXXX
  const cfrRegex = /(?:§|14\s*CFR\s*)(\d+\.\d+(?:\([a-z]\))?)/gi;
  while ((match = cfrRegex.exec(content)) !== null) {
    citations.add(`§${match[1]}`);
  }
  
  // Advisory Circulars: AC XX-XXX
  const acRegex = /AC\s*(\d+-\d+[A-Z]?)/gi;
  while ((match = acRegex.exec(content)) !== null) {
    citations.add(`AC ${match[1]}`);
  }
  
  // Technical Standard Orders: TSO-CXXX
  const tsoRegex = /TSO[-\s]?(C\d+[a-z]?)/gi;
  while ((match = tsoRegex.exec(content)) !== null) {
    citations.add(`TSO-${match[1].toUpperCase()}`);
  }
  
  return Array.from(citations);
}

/**
 * Extracts NRC citations from message content (e.g., 10 CFR 21.21, ML12345678)
 */
function extractNrcCitations(content: string): string[] {
  const citations = new Set<string>();
  let match;
  
  // NRC CFR references: 10 CFR XX.XXX or 10 CFR §XX.XXX(a)
  const nrcCfrRegex = /10\s*CFR\s*§?\s*(\d+\.\d+)(?:\([a-z]\))?/gi;
  while ((match = nrcCfrRegex.exec(content)) !== null) {
    citations.add(`10 CFR ${match[1]}`);
  }
  
  // ADAMS Accession Numbers: MLXXXXXXXX
  const adamsRegex = /\b(ML\d{8,})\b/gi;
  while ((match = adamsRegex.exec(content)) !== null) {
    citations.add(match[1].toUpperCase());
  }
  
  // NUREG reports: NUREG-XXXX or NUREG/CR-XXXX
  const nuregRegex = /\b(NUREG(?:\/CR)?-\d+)\b/gi;
  while ((match = nuregRegex.exec(content)) !== null) {
    citations.add(match[1].toUpperCase());
  }
  
  // Regulatory Guides: RG X.XXX or Regulatory Guide X.XXX
  const rgRegex = /(?:Regulatory\s+Guide|RG)\s*(\d+\.\d+)/gi;
  while ((match = rgRegex.exec(content)) !== null) {
    citations.add(`RG ${match[1]}`);
  }
  
  // Generic Letters: GL XX-XX
  const glRegex = /\bGL\s*(\d{2,4}-\d+)/gi;
  while ((match = glRegex.exec(content)) !== null) {
    citations.add(`GL ${match[1]}`);
  }
  
  // Information Notices: IN XXXX-XX
  const inRegex = /\bIN\s*(\d{2,4}-\d+)/gi;
  while ((match = inRegex.exec(content)) !== null) {
    citations.add(`IN ${match[1]}`);
  }
  
  // ANSI standards: ANSI N13.11 or ANSI/HPS N13.11
  const ansiRegex = /\bANSI(?:\/[A-Z]+)?\s+([A-Z]?\d+\.\d+)/gi;
  while ((match = ansiRegex.exec(content)) !== null) {
    citations.add(`ANSI ${match[1]}`);
  }
  
  return Array.from(citations);
}

/**
 * Extracts DoD citations from message content (e.g., FAR 52.204-21, DFARS 252.204-7012)
 */
function extractDodCitations(content: string): string[] {
  const citations = new Set<string>();
  let match;
  
  // FAR clause references: FAR 52.XXX-XX or FAR Part XX
  const farClauseRegex = /\bFAR\s+(\d+\.\d+-\d+)/gi;
  while ((match = farClauseRegex.exec(content)) !== null) {
    citations.add(`FAR ${match[1]}`);
  }
  
  const farPartRegex = /\bFAR\s+(?:Part\s+)?(\d+(?:\.\d+)?)/gi;
  while ((match = farPartRegex.exec(content)) !== null) {
    // Only add if not already captured as a clause
    const ref = `FAR ${match[1]}`;
    if (!Array.from(citations).some(c => c.startsWith(`FAR ${match[1]}`))) {
      citations.add(ref);
    }
  }
  
  // DFARS clause references: DFARS 252.XXX-XXXX
  const dfarsClauseRegex = /\bDFARS\s+(\d+\.\d+-\d+)/gi;
  while ((match = dfarsClauseRegex.exec(content)) !== null) {
    citations.add(`DFARS ${match[1]}`);
  }
  
  // Title 48 CFR references: 48 CFR XX.XXX or 48 CFR §XX.XXX
  const title48Regex = /48\s*CFR\s*§?\s*(\d+\.\d+(?:-\d+)?)/gi;
  while ((match = title48Regex.exec(content)) !== null) {
    citations.add(`48 CFR ${match[1]}`);
  }
  
  // Title 32 CFR references: 32 CFR Part XXX or 32 CFR §XX.XXX
  const title32Regex = /32\s*CFR\s*(?:Part\s+)?§?\s*(\d+(?:\.\d+)?)/gi;
  while ((match = title32Regex.exec(content)) !== null) {
    citations.add(`32 CFR ${match[1]}`);
  }
  
  // NIST SP references: NIST SP 800-171, NIST SP 800-53
  const nistRegex = /\bNIST\s+SP\s+(\d+-\d+)/gi;
  while ((match = nistRegex.exec(content)) !== null) {
    citations.add(`NIST SP ${match[1]}`);
  }
  
  // CMMC references: CMMC Level X or CMMC 2.0
  const cmmcRegex = /\bCMMC\s+(?:Level\s+)?(\d(?:\.\d)?)/gi;
  while ((match = cmmcRegex.exec(content)) !== null) {
    citations.add(`CMMC ${match[1]}`);
  }
  
  return Array.from(citations);
}

/**
 * Extracts citations based on current agent type
 */
function extractCitations(content: string): string[] {
  switch (AGENT) {
    case 'nrc':
      return extractNrcCitations(content);
    case 'dod':
      return extractDodCitations(content);
    default:
      return extractFaaCitations(content);
  }
}

/**
 * Chat store - manages conversation state and WebSocket communication
 * Uses SolidJS store for fine-grained reactivity (no full re-renders on text updates)
 */
export function createChatStore(
  token: string, 
  onQuotaExhausted?: (message: string) => void,
  onQuotaUpdate?: (used: number, remaining: number) => void,
  onAuthFailed?: () => void
) {
  const conversationId = getConversationId();
  const [messages, setMessages] = createStore<Message[]>([]);
  const [isLoading, setIsLoading] = createSignal(false);
  const [connectionStatus, setConnectionStatus] = createSignal<ConnectionStatus>('disconnected');
  
  // Current streaming message state
  let currentMessageIndex: number = -1;
  let currentContent = '';
  let currentToolCalls: ToolCall[] = [];
  
  // Batching for text updates - accumulate content and flush periodically
  let pendingContent = '';
  let flushScheduled = false;
  
  const ws = createWebSocket(conversationId, token);
  
  // Register quota exhausted handler
  if (onQuotaExhausted) {
    ws.onTrialExhausted(onQuotaExhausted);
  }
  
  // Register quota update handler
  if (onQuotaUpdate) {
    ws.onQuotaUpdate(onQuotaUpdate);
  }
  
  // Register auth failed handler
  if (onAuthFailed) {
    ws.onAuthFailed(onAuthFailed);
  }
  
  // Sync connection status
  createEffect(() => {
    setConnectionStatus(ws.status());
  });
  
  function flushContent() {
    if (pendingContent && currentMessageIndex >= 0) {
      currentContent += pendingContent;
      pendingContent = '';
      // Use produce for surgical update - only updates the content field
      setMessages(currentMessageIndex, 'content', currentContent);
    }
    flushScheduled = false;
  }
  
  function scheduleFlush() {
    if (!flushScheduled) {
      flushScheduled = true;
      requestAnimationFrame(flushContent);
    }
  }
  
  // Handle incoming WebSocket events
  let totalChunks = 0;
  let totalChars = 0;
  
  ws.onEvent((event: WebSocketEvent) => {
    logger.debug('store', `Event received: ${event.type}`, event.type === 'text' ? { chars: event.content.length } : undefined);
    
    switch (event.type) {
      case 'text':
        totalChunks++;
        totalChars += event.content.length;
        handleTextEvent(event.content);
        break;
      case 'tool_use':
        handleToolUse(event.name);
        break;
      case 'tool_executing':
        handleToolExecuting(event.tool, event.input);
        break;
      case 'tool_result':
        handleToolResult(event.tool, event.result);
        break;
      case 'error':
        handleError(event.content);
        break;
      case 'done':
        handleDone();
        break;
    }
  });
  
  function handleTextEvent(content: string) {
    if (currentMessageIndex < 0) {
      // Start new assistant message
      const newMessage: Message = {
        id: generateId(),
        role: 'assistant',
        content: '',
        toolCalls: [],
        timestamp: new Date(),
        isStreaming: true,
      };
      
      currentMessageIndex = messages.length;
      currentContent = '';
      currentToolCalls = [];
      
      setMessages(produce((msgs) => {
        msgs.push(newMessage);
      }));
    }
    
    // Batch content updates
    pendingContent += content;
    scheduleFlush();
  }
  
  function handleToolUse(name: string) {
    // Flush any pending content first
    flushContent();
    
    const newTool: ToolCall = { name, status: 'pending' };
    currentToolCalls.push(newTool);
    
    if (currentMessageIndex >= 0) {
      setMessages(currentMessageIndex, 'toolCalls', [...currentToolCalls]);
    }
  }
  
  function handleToolExecuting(tool: string, input: Record<string, unknown>) {
    const toolIndex = currentToolCalls.findIndex(t => t.name === tool && t.status === 'pending');
    if (toolIndex >= 0) {
      currentToolCalls[toolIndex].status = 'executing';
      currentToolCalls[toolIndex].input = input;
      
      if (currentMessageIndex >= 0) {
        setMessages(currentMessageIndex, 'toolCalls', [...currentToolCalls]);
      }
    }
  }
  
  function handleToolResult(tool: string, result: string) {
    const toolIndex = currentToolCalls.findIndex(t => t.name === tool && t.status === 'executing');
    if (toolIndex >= 0) {
      currentToolCalls[toolIndex].status = 'done';
      currentToolCalls[toolIndex].result = result;
      
      if (currentMessageIndex >= 0) {
        setMessages(currentMessageIndex, 'toolCalls', [...currentToolCalls]);
      }
    }
  }
  
  function handleError(content: string) {
    logger.error('store', 'handleError', { content, contentSoFar: currentContent.length });
    
    // Check if this is a trial exhaustion error - don't add to messages, let the handler deal with it
    if (content.includes("used your") && content.includes("requests")) {
      logger.warn('store', 'Trial exhaustion error detected, delegating to handler');
      onTrialExhausted?.(content);
      setIsLoading(false);
      return;
    }
    
    flushContent();
    
    if (currentMessageIndex >= 0) {
      currentContent += `\n\n**Error:** ${content}`;
      setMessages(currentMessageIndex, 'content', currentContent);
    } else {
      setMessages(produce((msgs) => {
        msgs.push({
          id: generateId(),
          role: 'assistant',
          content: `**Error:** ${content}`,
          timestamp: new Date(),
        });
      }));
    }
    setIsLoading(false);
  }
  
  function handleDone() {
    // Flush any remaining content
    flushContent();
    
    logger.info('store', 'handleDone', {
      totalChunks,
      totalChars,
      finalLength: currentContent.length,
      preview: currentContent.slice(0, 200),
      ending: currentContent.slice(-100),
    });
    
    if (currentMessageIndex >= 0) {
      // Finalize message - batch all final updates
      batch(() => {
        setMessages(currentMessageIndex, 'content', currentContent);
        setMessages(currentMessageIndex, 'toolCalls', [...currentToolCalls]);
        setMessages(currentMessageIndex, 'citations', extractCitations(currentContent));
        setMessages(currentMessageIndex, 'isStreaming', false);
      });
    }
    
    // Reset counters for next message
    totalChunks = 0;
    totalChars = 0;
    currentMessageIndex = -1;
    currentContent = '';
    currentToolCalls = [];
    setIsLoading(false);
  }
  
  function sendMessage(content: string) {
    if (!content.trim() || isLoading()) return;
    
    // Add user message
    setMessages(produce((msgs) => {
      msgs.push({
        id: generateId(),
        role: 'user',
        content: content.trim(),
        timestamp: new Date(),
      });
    }));
    
    setIsLoading(true);
    
    // Send to backend
    if (!ws.send(content.trim())) {
      handleError('Not connected to server');
    }
  }
  
  function clearConversation() {
    setMessages([]);
    currentMessageIndex = -1;
    currentContent = '';
    currentToolCalls = [];
    
    // Generate new conversation ID
    const newId = `conv-${generateId()}`;
    sessionStorage.setItem(`${branding.sessionStoragePrefix}-conversation-id`, newId);
    
    ws.disconnect();
  }
  
  // Connect on mount
  ws.connect();
  
  // Cleanup on unmount
  onCleanup(() => {
    ws.disconnect();
  });
  
  return {
    get messages() { return messages; },
    isLoading,
    connectionStatus,
    sendMessage,
    clearConversation,
  };
}
