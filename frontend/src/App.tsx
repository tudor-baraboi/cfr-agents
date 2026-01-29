import { Component, createSignal, onMount, For, Show } from 'solid-js';
import { createChatStore } from './store';
import MessageBubble from './MessageBubble';
import Login from './Login';
import FeedbackModal from './FeedbackModal';
import AdminDashboard from './AdminDashboard';
import MyDocumentsPanel from './MyDocumentsPanel';
import type { ConnectionStatus, AuthState, QuotaExhaustedState } from './types';
import { branding, exampleQueries } from './config';
import { logger } from './logger';

const API_URL = import.meta.env.VITE_API_URL || '';

/**
 * Detect route from pathname
 * /admin - Admin dashboard
 * /infinity - Unlimited chat mode (admin auth)
 * / or anything else - Normal fingerprint auth chat
 */
type AppRoute = 'chat' | 'admin' | 'infinity';

function getRoute(): AppRoute {
  const path = window.location.pathname;
  if (path === '/admin' || path === '/admin/') return 'admin';
  if (path === '/infinity' || path === '/infinity/') return 'infinity';
  return 'chat';
}

const Header: Component<{ status: ConnectionStatus; token: string }> = (props) => {
  const [showFeedback, setShowFeedback] = createSignal(false);
  
  const statusText = () => {
    switch (props.status) {
      case 'connected': return 'Connected';
      case 'connecting': return 'Connecting...';
      case 'disconnected': return 'Disconnected';
    }
  };
  
  return (
    <header class="header">
      <svg class="header-logo" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="45" fill={branding.primaryColor} />
        <text x="50" y="65" font-family="Arial, sans-serif" font-size="40" font-weight="bold" fill="white" text-anchor="middle">{branding.logoText}</text>
      </svg>
      <div>
        <h1 class="header-title">{branding.title}</h1>
        <p class="header-subtitle">{branding.subtitle}</p>
      </div>
      <div class="header-actions">
        <button 
          class="feedback-btn" 
          onClick={() => setShowFeedback(true)}
          title="Send feedback"
        >
          💬
        </button>
        <div class="connection-status">
          <span class={`status-dot ${props.status}`} />
          <span>{statusText()}</span>
        </div>
      </div>
      <FeedbackModal 
        isOpen={showFeedback()} 
        onClose={() => setShowFeedback(false)} 
        token={props.token} 
      />
    </header>
  );
};

const WelcomeScreen: Component<{ onSelectQuery: (query: string) => void }> = (props) => (
  <div class="welcome">
    <svg class="welcome-icon" viewBox="0 0 100 100">
      <circle cx="50" cy="50" r="45" fill={branding.primaryColor} opacity="0.2" />
      <text x="50" y="65" font-family="Arial, sans-serif" font-size="40" font-weight="bold" fill={branding.primaryColor} text-anchor="middle">{branding.logoText}</text>
    </svg>
    <h2 class="welcome-title">{branding.welcomeTitle}</h2>
    <p class="welcome-text">{branding.welcomeText}</p>
    <div class="example-queries">
      <For each={exampleQueries}>
        {(query) => (
          <button class="example-query" onClick={() => props.onSelectQuery(query)}>
            {query}
          </button>
        )}
      </For>
    </div>
  </div>
);

/**
 * Quota Exhausted Screen - shown when user has used all their daily requests
 */
const QuotaExhaustedScreen: Component<{ message: string }> = (props) => (
  <div class="login-container">
    <div class="login-card">
      <svg class="login-logo" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="45" fill={branding.primaryColor} />
        <text x="50" y="65" font-family="Arial, sans-serif" font-size="40" font-weight="bold" fill="white" text-anchor="middle">{branding.logoText}</text>
      </svg>
      
      <h1 class="login-title">Daily Limit Reached</h1>
      <p class="trial-exhausted-message">{props.message}</p>
      
      <p class="login-help">
        Your queries will reset at midnight UTC
      </p>
    </div>
  </div>
);

/**
 * Main chat interface - only shown when authenticated
 */
const ChatInterface: Component<{ 
  auth: AuthState; 
  onQuotaExhausted: (message: string) => void;
  onQuotaUpdate: (used: number, remaining: number) => void;
  onAuthFailed: () => void;
}> = (props) => {
  const store = createChatStore(props.auth.token!, props.onQuotaExhausted, props.onQuotaUpdate, props.onAuthFailed);
  const [inputValue, setInputValue] = createSignal('');
  let messagesContainer: HTMLDivElement | undefined;
  let inputField: HTMLTextAreaElement | undefined;
  
  // Simple scroll to bottom
  const scrollToBottom = () => {
    if (messagesContainer) {
      messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
  };
  
  onMount(() => {
    if (messagesContainer) {
      const observer = new MutationObserver(scrollToBottom);
      observer.observe(messagesContainer, { childList: true, subtree: true, characterData: true });
    }
  });
  
  const handleSubmit = (e: Event) => {
    e.preventDefault();
    const value = inputValue().trim();
    if (value && !store.isLoading()) {
      store.sendMessage(value);
      setInputValue('');
      if (inputField) {
        inputField.style.height = 'auto';
      }
    }
  };
  
  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };
  
  const handleInput = (e: Event) => {
    const target = e.target as HTMLTextAreaElement;
    setInputValue(target.value);
    // Auto-resize textarea
    target.style.height = 'auto';
    target.style.height = `${Math.min(target.scrollHeight, 200)}px`;
  };
  
  const handleExampleQuery = (query: string) => {
    store.sendMessage(query);
  };
  
  /**
   * Get the preceding user message for a given message index
   * Used to pass the question to assistant messages for PDF export
   */
  const getQuestionForMessage = (index: number): string | undefined => {
    // For assistant messages, find the previous user message
    const message = store.messages[index];
    if (message.role !== 'assistant') return undefined;
    
    // Look backwards for the nearest user message
    for (let i = index - 1; i >= 0; i--) {
      if (store.messages[i].role === 'user') {
        return store.messages[i].content;
      }
    }
    return undefined;
  };
  
  return (
    <div class="app">
      <Header status={store.connectionStatus()} token={props.auth.token!} />
      
      <Show
        when={store.messages.length > 0}
        fallback={<WelcomeScreen onSelectQuery={handleExampleQuery} />}
      >
        <div class="messages" ref={messagesContainer}>
          <For each={store.messages}>
            {(message, index) => (
              <MessageBubble 
                message={message} 
                question={getQuestionForMessage(index())} 
              />
            )}
          </For>
        </div>
      </Show>
      
      <div class="input-area">
        <Show when={!props.auth.isAdmin && props.auth.dailyLimit > 0}>
          <div class="quota-display">
            {props.auth.requestsRemaining} of {props.auth.dailyLimit} queries remaining today
          </div>
        </Show>
        <form class="input-form" onSubmit={handleSubmit}>
          <textarea
            ref={inputField}
            class="input-field"
            placeholder={branding.placeholder}
            value={inputValue()}
            onInput={handleInput}
            onKeyDown={handleKeyDown}
            disabled={store.connectionStatus() !== 'connected'}
            rows={1}
          />
          <button
            type="submit"
            class="send-button"
            disabled={store.isLoading() || !inputValue().trim() || store.connectionStatus() !== 'connected'}
          >
            {store.isLoading() ? '...' : 'Send'}
          </button>
        </form>
      </div>
      
      {/* FAB for My Documents - renders as fixed positioned overlay */}
      <Show when={props.auth.fingerprint}>
        <MyDocumentsPanel 
          token={props.auth.token!} 
          fingerprint={props.auth.fingerprint!} 
        />
      </Show>
    </div>
  );
};

/**
 * Main App component - handles auth state and renders Login or Chat
 */
const App: Component = () => {
  const [auth, setAuth] = createSignal<AuthState | null>(null);
  const [quotaExhausted, setQuotaExhausted] = createSignal<QuotaExhaustedState | null>(null);
  const route = getRoute();
  
  // Check for existing token on mount
  onMount(() => {
    // For admin routes, use a separate session storage key
    const storageKey = route === 'chat' 
      ? `${branding.sessionStoragePrefix}-auth-token`
      : `${branding.sessionStoragePrefix}-admin-token`;
    const token = sessionStorage.getItem(storageKey);
    const fingerprint = sessionStorage.getItem(`${branding.sessionStoragePrefix}-fingerprint`) || undefined;
    
    if (token) {
      const isAdmin = route !== 'chat' || sessionStorage.getItem(`${branding.sessionStoragePrefix}-is-admin`) === 'true';
      // We have a token - assume it's valid (will fail on WS connect if not)
      setAuth({
        token,
        isAdmin,
        requestsUsed: 0,
        requestsRemaining: isAdmin ? 999 : 15,
        dailyLimit: isAdmin ? 0 : 15,
        fingerprint,
      });
    }
  });
  
  const handleLogin = (authState: AuthState) => {
    setAuth(authState);
  };
  
  const handleQuotaExhausted = (message: string) => {
    logger.warn('App', 'Quota exhausted', { message });
    // Clear auth token so user can't try to use it again
    sessionStorage.removeItem(`${branding.sessionStoragePrefix}-auth-token`);
    sessionStorage.removeItem(`${branding.sessionStoragePrefix}-conversation-id`);
    setAuth(null);
    setQuotaExhausted({ exhausted: true, message });
  };
  
  const handleQuotaUpdate = (used: number, remaining: number) => {
    const current = auth();
    if (current) {
      setAuth({
        ...current,
        requestsUsed: used,
        requestsRemaining: remaining,
      });
    }
  };
  
  const handleAuthFailed = () => {
    logger.warn('App', 'Auth failed - clearing session and forcing re-auth');
    // Clear all auth-related session storage
    sessionStorage.removeItem(`${branding.sessionStoragePrefix}-auth-token`);
    sessionStorage.removeItem(`${branding.sessionStoragePrefix}-admin-token`);
    sessionStorage.removeItem(`${branding.sessionStoragePrefix}-is-admin`);
    sessionStorage.removeItem(`${branding.sessionStoragePrefix}-conversation-id`);
    // Reset auth state to force re-login
    setAuth(null);
  };
  
  // /admin route - show admin dashboard after login
  if (route === 'admin') {
    return (
      <Show
        when={auth()}
        fallback={<Login onLogin={handleLogin} mode="admin" />}
      >
        {(authState) => <AdminDashboard token={authState().token!} />}
      </Show>
    );
  }
  
  // /infinity route - show chat with unlimited access after admin login
  if (route === 'infinity') {
    return (
      <Show
        when={auth()}
        fallback={<Login onLogin={handleLogin} mode="infinity" />}
      >
        {(authState) => (
          <ChatInterface 
            auth={{ ...authState(), isAdmin: true, dailyLimit: 0, requestsRemaining: 999 }} 
            onQuotaExhausted={handleQuotaExhausted}
            onQuotaUpdate={handleQuotaUpdate}
            onAuthFailed={handleAuthFailed}
          />
        )}
      </Show>
    );
  }
  
  // Default route - normal fingerprint auth
  return (
    <Show
      when={quotaExhausted()?.exhausted}
      fallback={
        <Show
          when={auth()}
          fallback={<Login onLogin={handleLogin} mode="fingerprint" />}
        >
          {(authState) => (
            <ChatInterface 
              auth={authState()} 
              onQuotaExhausted={handleQuotaExhausted}
              onQuotaUpdate={handleQuotaUpdate}
              onAuthFailed={handleAuthFailed}
            />
          )}
        </Show>
      }
    >
      <QuotaExhaustedScreen message={quotaExhausted()?.message || "You've used all your daily queries. Come back tomorrow!"} />
    </Show>
  );
};

export default App;
