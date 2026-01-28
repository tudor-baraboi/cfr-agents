import { Component, For, Show, createSignal, createEffect, onCleanup, createMemo } from 'solid-js';
import { marked } from 'marked';
import type { Message, ToolCall } from './types';
import { exportToPdf } from './exportPdf';

// Configure marked for safe rendering
marked.setOptions({
  breaks: true,
  gfm: true,
});

/**
 * Splits content into thinking (pre-response reasoning) and response (actual markdown)
 * The response typically starts with a heading (# or ##) or a clear paragraph break
 */
function splitThinkingAndResponse(content: string): { thinking: string; response: string } {
  if (!content) return { thinking: '', response: '' };
  
  // Look for markdown structure that indicates the "real" response is starting
  // Common patterns: headings, bullet lists after blank line, or clear paragraph breaks
  const responsePatterns = [
    /\n\n##?\s+[A-Z]/,           // Heading starting with capital letter
    /\n\n\*\*[A-Z][^*]+\*\*/,   // Bold text starting paragraph  
    /\n\n(?:The |Based on |According to |Here |I found )/,  // Common response starters
    /\n\n(?:1\.|•|-)\s+/,       // Numbered or bulleted list
  ];
  
  for (const pattern of responsePatterns) {
    const match = content.match(pattern);
    if (match && match.index !== undefined) {
      return {
        thinking: content.slice(0, match.index).trim(),
        response: content.slice(match.index).trim(),
      };
    }
  }
  
  // No clear split found - if content has markdown structure, treat it all as response
  if (content.match(/^##?\s+|^\*\*|^(?:1\.|•|-)\s+/m)) {
    return { thinking: '', response: content };
  }
  
  // Otherwise it's all thinking (still waiting for response)
  return { thinking: content, response: '' };
}

interface MessageBubbleProps {
  message: Message;
  question?: string; // The user's question (for assistant messages)
}

const ToolIcon: Component = () => (
  <svg class="tool-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
  </svg>
);

const ToolCallDisplay: Component<{ tool: ToolCall }> = (props) => {
  const statusText = () => {
    switch (props.tool.status) {
      case 'pending': return 'starting...';
      case 'executing': return 'running';
      case 'done': return 'done';
    }
  };
  
  const friendlyName = () => {
    const names: Record<string, string> = {
      'search_indexed_content': 'Searching documents',
      'fetch_cfr_section': 'Fetching CFR section',
      'fetch_drs_document': 'Fetching advisory circular',
      'search_drs': 'Searching DRS',
      'get_cfr_references': 'Getting references',
    };
    return names[props.tool.name] || props.tool.name;
  };
  
  return (
    <div class="tool-call">
      <ToolIcon />
      <span class="tool-name">{friendlyName()}</span>
      <span class={`tool-status ${props.tool.status}`}>{statusText()}</span>
    </div>
  );
};

const Citations: Component<{ citations: string[] }> = (props) => (
  <div class="citations">
    <div class="citations-title">References</div>
    <For each={props.citations}>
      {(citation) => (
        <span class="citation">{citation}</span>
      )}
    </For>
  </div>
);

/**
 * Streaming markdown renderer with throttled updates
 * Renders markdown incrementally for smooth streaming experience
 */
const StreamingMarkdown: Component<{ content: string; isStreaming: boolean }> = (props) => {
  const [renderedHtml, setRenderedHtml] = createSignal('');
  let lastRenderTime = 0;
  let pendingRender: number | null = null;
  
  const RENDER_INTERVAL = 50; // Render at most every 50ms for smooth updates
  
  const renderMarkdown = (content: string) => {
    try {
      const html = marked.parse(content) as string;
      setRenderedHtml(html);
    } catch {
      // Fallback to plain text if markdown parsing fails
      setRenderedHtml(`<p>${content}</p>`);
    }
  };
  
  createEffect(() => {
    const content = props.content;
    const isStreaming = props.isStreaming;
    
    if (!content) {
      setRenderedHtml('');
      return;
    }
    
    // If not streaming, render immediately
    if (!isStreaming) {
      if (pendingRender) {
        cancelAnimationFrame(pendingRender);
        pendingRender = null;
      }
      renderMarkdown(content);
      return;
    }
    
    // Throttle renders during streaming
    const now = performance.now();
    const timeSinceLastRender = now - lastRenderTime;
    
    if (timeSinceLastRender >= RENDER_INTERVAL) {
      // Enough time has passed, render now
      lastRenderTime = now;
      renderMarkdown(content);
    } else if (!pendingRender) {
      // Schedule a render for later
      pendingRender = requestAnimationFrame(() => {
        pendingRender = null;
        lastRenderTime = performance.now();
        renderMarkdown(props.content);
      });
    }
  });
  
  onCleanup(() => {
    if (pendingRender) {
      cancelAnimationFrame(pendingRender);
    }
  });
  
  return (
    <div 
      class="markdown-content" 
      classList={{ 'is-streaming': props.isStreaming }}
      innerHTML={renderedHtml()} 
    />
  );
};

/**
 * Thinking/reasoning display - shows Claude's thought process in a collapsible, dimmed style
 */
const ThinkingDisplay: Component<{ content: string; isCollapsed: boolean }> = (props) => {
  // Split thinking content into separate thoughts for better readability
  const thoughts = createMemo(() => {
    const text = props.content;
    if (!text) return [];
    
    // Split on common patterns like "Now let me...", "Let me also...", etc.
    const parts = text.split(/(?=(?:Now |Let me |I'll |Perfect|Good))/g)
      .map(s => s.trim())
      .filter(s => s.length > 0);
    
    return parts.length > 0 ? parts : [text];
  });
  
  return (
    <Show when={props.content}>
      <div class="thinking-process" classList={{ collapsed: props.isCollapsed }}>
        <div class="thinking-header">
          <svg class="thinking-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 16v-4M12 8h.01" />
          </svg>
          <span>Reasoning</span>
        </div>
        <div class="thinking-content">
          <For each={thoughts()}>
            {(thought) => <p class="thought">{thought}</p>}
          </For>
        </div>
      </div>
    </Show>
  );
};

const MessageBubble: Component<MessageBubbleProps> = (props) => {
  const [isExporting, setIsExporting] = createSignal(false);
  const hasToolCalls = () => props.message.toolCalls && props.message.toolCalls.length > 0;
  const hasCitations = () => props.message.citations && props.message.citations.length > 0;
  const isStreaming = () => props.message.isStreaming ?? false;
  const hasContent = () => !!props.message.content;
  
  // Split content into thinking and response parts
  const contentParts = createMemo(() => splitThinkingAndResponse(props.message.content || ''));
  const hasThinking = () => contentParts().thinking.length > 0;
  const hasResponse = () => contentParts().response.length > 0;
  
  // Can export if assistant message with response content, not streaming, and has a question
  const canExport = () => 
    props.message.role === 'assistant' && 
    hasResponse() && 
    !isStreaming() && 
    !!props.question;
  
  const handleExport = async () => {
    if (!canExport() || isExporting()) return;
    
    setIsExporting(true);
    try {
      await exportToPdf({
        question: props.question!,
        response: contentParts().response,
        citations: props.message.citations,
        timestamp: props.message.timestamp,
      });
    } catch (err) {
      console.error('Failed to export PDF:', err);
    } finally {
      setIsExporting(false);
    }
  };
  
  return (
    <div class={`message ${props.message.role}`} classList={{ streaming: isStreaming() }}>
      <div class="message-content">
        <Show when={props.message.role === 'assistant'}>
          <Show 
            when={hasContent()} 
            fallback={
              <Show when={isStreaming()}>
                <div class="thinking-indicator">
                  <span class="thinking-dot" />
                  <span class="thinking-dot" />
                  <span class="thinking-dot" />
                </div>
              </Show>
            }
          >
            {/* Show thinking process - collapsed once response starts */}
            <ThinkingDisplay 
              content={contentParts().thinking} 
              isCollapsed={hasResponse()} 
            />
            
            {/* Show actual response */}
            <Show when={hasResponse()}>
              <StreamingMarkdown 
                content={contentParts().response} 
                isStreaming={isStreaming()} 
              />
            </Show>
            
            {/* If only thinking (no response yet), show streaming cursor */}
            <Show when={hasThinking() && !hasResponse() && isStreaming()}>
              <div class="streaming-cursor" />
            </Show>
          </Show>
          
          {/* Download button - at bottom, only shown when not streaming and has content */}
          <Show when={canExport()}>
            <button 
              class="download-btn" 
              onClick={handleExport}
              disabled={isExporting()}
              title="Export to PDF"
            >
              {isExporting() ? '⏳' : 'PDF ↓'}
            </button>
          </Show>
        </Show>
        <Show when={props.message.role === 'user'}>
          <div class="user-content">{props.message.content}</div>
        </Show>
      </div>
      
      <Show when={hasToolCalls()}>
        <div class="tool-activity">
          <For each={props.message.toolCalls}>
            {(tool) => <ToolCallDisplay tool={tool} />}
          </For>
        </div>
      </Show>
      
      <Show when={hasCitations() && !isStreaming()}>
        <Citations citations={props.message.citations!} />
      </Show>
    </div>
  );
};

export default MessageBubble;
