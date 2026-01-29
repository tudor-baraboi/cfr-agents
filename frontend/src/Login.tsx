import { Component, createSignal, onMount, Show } from 'solid-js';
import type { AuthState, ValidateCodeResponse, FingerprintResponse } from './types';
import { branding } from './config';
import { getVisitorId } from './fingerprint';

// Backend API URL
const API_URL = import.meta.env.VITE_API_URL || '';

/**
 * Login modes:
 * - fingerprint: Auto-authenticate with browser fingerprint (default)
 * - admin: Require admin code, redirect to admin dashboard
 * - infinity: Require admin code, redirect to unlimited chat
 */
type LoginMode = 'fingerprint' | 'admin' | 'infinity';

interface LoginProps {
  onLogin: (auth: AuthState) => void;
  mode?: LoginMode;
}

const Login: Component<LoginProps> = (props) => {
  const [code, setCode] = createSignal('');
  const [error, setError] = createSignal('');
  const [isLoading, setIsLoading] = createSignal(false);
  const [status, setStatus] = createSignal('Initializing...');
  
  const mode = () => props.mode || 'fingerprint';
  const requiresAdminCode = () => mode() === 'admin' || mode() === 'infinity';

  // Auto-authenticate with fingerprint on mount (unless admin mode)
  onMount(async () => {
    if (requiresAdminCode()) {
      return; // Admin mode - wait for code entry
    }
    
    setIsLoading(true);
    setStatus('Identifying browser...');
    
    try {
      const visitorId = await getVisitorId();
      setStatus('Authenticating...');
      
      const baseUrl = API_URL || window.location.origin;
      const response = await fetch(`${baseUrl}/auth/fingerprint`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ visitor_id: visitorId }),
      });

      if (!response.ok) {
        const data = await response.json();
        setError(data.detail || 'Authentication failed');
        setIsLoading(false);
        return;
      }

      const data: FingerprintResponse = await response.json();
      
      // Store token, admin status, and fingerprint in sessionStorage
      sessionStorage.setItem(`${branding.sessionStoragePrefix}-auth-token`, data.token);
      sessionStorage.setItem(`${branding.sessionStoragePrefix}-is-admin`, data.is_admin ? 'true' : 'false');
      sessionStorage.setItem(`${branding.sessionStoragePrefix}-fingerprint`, visitorId);
      
      // Notify parent
      props.onLogin({
        token: data.token,
        isAdmin: data.is_admin,
        requestsUsed: data.requests_used,
        requestsRemaining: data.requests_remaining,
        dailyLimit: data.daily_limit,
        fingerprint: visitorId,
      });
    } catch (err) {
      console.error('Auto-auth error:', err);
      setError('Failed to connect. Please try again.');
      setIsLoading(false);
    }
  });

  // Admin code submission
  const handleSubmit = async (e: Event) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    const trimmedCode = code().trim().toUpperCase();
    if (!trimmedCode) {
      setError('Please enter an access code');
      setIsLoading(false);
      return;
    }

    try {
      // For infinity mode, get fingerprint BEFORE sending request so it can be included in JWT
      let fingerprint: string | undefined;
      if (mode() === 'infinity') {
        try {
          fingerprint = await getVisitorId();
        } catch (fpError) {
          console.warn('Failed to get fingerprint for infinity mode:', fpError);
        }
      }

      const baseUrl = API_URL || window.location.origin;
      const response = await fetch(`${baseUrl}/auth/validate-code`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
          code: trimmedCode,
          fingerprint: fingerprint,  // Include fingerprint for My Documents feature
        }),
      });

      if (!response.ok) {
        const data = await response.json();
        setError(data.detail || 'Invalid access code');
        setIsLoading(false);
        return;
      }

      const data: ValidateCodeResponse = await response.json();
      
      // Store token in sessionStorage (use separate key for admin routes)
      sessionStorage.setItem(`${branding.sessionStoragePrefix}-admin-token`, data.token);
      
      // Also store fingerprint in sessionStorage for My Documents feature
      if (fingerprint) {
        sessionStorage.setItem(`${branding.sessionStoragePrefix}-fingerprint`, fingerprint);
      }
      
      // Notify parent
      props.onLogin({
        token: data.token,
        isAdmin: data.is_admin,
        requestsUsed: data.requests_used,
        requestsRemaining: data.requests_remaining ?? 0,
        dailyLimit: 0,  // Admin has unlimited
        fingerprint,
      });
    } catch (err) {
      console.error('Login error:', err);
      setError('Failed to connect. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };
  
  const getTitle = () => {
    switch (mode()) {
      case 'admin': return 'Admin Dashboard';
      case 'infinity': return `${branding.title} ∞`;
      default: return branding.title;
    }
  };
  
  const getSubtitle = () => {
    switch (mode()) {
      case 'admin': return 'Enter your admin code to access the dashboard';
      case 'infinity': return 'Enter your admin code for unlimited access';
      default: return `Welcome to ${branding.title}`;
    }
  };

  // Generate spiky urchin paths
  const generateUrchinSpikes = () => {
    const spikes: string[] = [];
    const cx = 50, cy = 50;
    const innerRadius = 18;
    const outerRadius = 45;
    const numSpikes = 24;
    
    for (let i = 0; i < numSpikes; i++) {
      const angle = (i * 2 * Math.PI) / numSpikes - Math.PI / 2;
      const x1 = cx + innerRadius * Math.cos(angle);
      const y1 = cy + innerRadius * Math.sin(angle);
      const x2 = cx + outerRadius * Math.cos(angle);
      const y2 = cy + outerRadius * Math.sin(angle);
      spikes.push(`M${x1},${y1} L${x2},${y2}`);
    }
    return spikes.join(' ');
  };

  return (
    <div class="login-container">
      <div class="login-card">
        <Show when={mode() === 'admin'} fallback={
          /* FAA logo for regular and infinity modes */
          <svg class="login-logo" viewBox="0 0 100 100">
            <circle cx="50" cy="50" r="45" fill={branding.primaryColor} />
            <text x="50" y="65" font-family="Arial, sans-serif" font-size="40" font-weight="bold" fill="white" text-anchor="middle">{branding.logoText}</text>
          </svg>
        }>
          {/* Urchin logo for admin mode */}
          <svg class="login-logo" viewBox="0 0 100 100">
            <path d={generateUrchinSpikes()} stroke={branding.primaryColor} stroke-width="3" stroke-linecap="round" fill="none" />
            <circle cx="50" cy="50" r="18" fill={branding.primaryColor} />
          </svg>
        </Show>
        
        <h1 class="login-title">{getTitle()}</h1>
        
        <Show when={requiresAdminCode()} fallback={
          /* Fingerprint auto-auth mode */
          <div class="login-auto">
            <p class="login-subtitle">{status()}</p>
            {error() && <p class="login-error">{error()}</p>}
            {isLoading() && !error() && (
              <div class="login-spinner"></div>
            )}
            {error() && (
              <button
                class="login-button"
                onClick={() => window.location.reload()}
              >
                Try Again
              </button>
            )}
          </div>
        }>
          {/* Admin code entry mode */}
          <p class="login-subtitle">{getSubtitle()}</p>
          
          <form class="login-form" onSubmit={handleSubmit}>
            <input
              type="password"
              class="login-input"
              placeholder="Admin Code"
              value={code()}
              onInput={(e) => setCode(e.currentTarget.value)}
              disabled={isLoading()}
              autocomplete="current-password"
              autofocus
            />
            
            {error() && <p class="login-error">{error()}</p>}
            
            <button
              type="submit"
              class="login-button"
              disabled={isLoading() || !code().trim()}
            >
              {isLoading() ? 'Validating...' : 'Continue'}
            </button>
          </form>
        </Show>
        
        <p class="login-help">
          {requiresAdminCode() ? '' : `Welcome to ${branding.title}`}
        </p>
      </div>
    </div>
  );
};

export default Login;
