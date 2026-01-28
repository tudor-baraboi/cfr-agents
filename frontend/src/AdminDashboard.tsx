/**
 * Admin Dashboard component for viewing usage statistics and feedback.
 * Only visible to authenticated admin users.
 */

import { Component, createSignal, onMount, onCleanup, For, Show } from 'solid-js';
import { branding } from './config';

const API_URL = import.meta.env.VITE_API_URL || '';

// Set admin-specific page title and favicon
const setAdminBranding = () => {
  document.title = 'eCFR Admin Dashboard';
  const favicon = document.querySelector('link[rel="icon"]') as HTMLLinkElement;
  if (favicon) {
    favicon.href = '/urchin-favicon.svg';
  }
};

// Restore normal branding
const restoreNormalBranding = () => {
  document.title = 'FAA Certification Agent';
  const favicon = document.querySelector('link[rel="icon"]') as HTMLLinkElement;
  if (favicon) {
    favicon.href = '/favicon.svg';
  }
};

interface UsageRecord {
  date: string;
  fingerprint: string;
  request_count: number;
  first_request_at: string | null;
  last_request_at: string | null;
  user_agent: string;
  ip_address: string;
  country: string;
  city: string;
}

interface FeedbackRecord {
  id: string;
  date: string;
  type: string;
  message: string;
  fingerprint: string;
  logs_url: string;
  user_agent: string;
  created_at: string | null;
  contact: {
    name?: string;
    email?: string;
    phone?: string;
    company?: string;
  } | null;
}

type TabType = 'usage' | 'feedback';

const formatDateTime = (isoString: string | null): string => {
  if (!isoString) return '-';
  try {
    const date = new Date(isoString);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return isoString;
  }
};

const truncate = (str: string, len: number): string => {
  if (!str) return '-';
  return str.length > len ? str.slice(0, len) + '...' : str;
};

const getTypeColor = (type: string): string => {
  switch (type.toLowerCase()) {
    case 'bug': return '#ef4444';
    case 'feature': return '#3b82f6';
    default: return '#6b7280';
  }
};

const AdminDashboard: Component<{ token: string }> = (props) => {
  const [activeTab, setActiveTab] = createSignal<TabType>('usage');
  const [usageData, setUsageData] = createSignal<UsageRecord[]>([]);
  const [feedbackData, setFeedbackData] = createSignal<FeedbackRecord[]>([]);
  const [loading, setLoading] = createSignal(false);
  const [error, setError] = createSignal<string | null>(null);

  const fetchUsage = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/admin/usage`, {
        headers: { Authorization: `Bearer ${props.token}` },
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setUsageData(data.usage || []);
    } catch (e) {
      setError(`Failed to fetch usage: ${e}`);
    } finally {
      setLoading(false);
    }
  };

  const fetchFeedback = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/admin/feedback`, {
        headers: { Authorization: `Bearer ${props.token}` },
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setFeedbackData(data.feedback || []);
    } catch (e) {
      setError(`Failed to fetch feedback: ${e}`);
    } finally {
      setLoading(false);
    }
  };

  onMount(() => {
    setAdminBranding();
    fetchUsage();
    fetchFeedback();
  });

  onCleanup(() => {
    restoreNormalBranding();
  });

  const handleTabChange = (tab: TabType) => {
    setActiveTab(tab);
  };

  // Generate urchin spikes for header logo
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
    <div class="admin-dashboard">
      <header class="admin-header">
        <svg class="header-logo" viewBox="0 0 100 100">
          <path d={generateUrchinSpikes()} stroke={branding.primaryColor} stroke-width="3" stroke-linecap="round" fill="none" />
          <circle cx="50" cy="50" r="18" fill={branding.primaryColor} />
        </svg>
        <div>
          <h1 class="header-title">Admin Dashboard</h1>
          <p class="header-subtitle">eCFR Agent - Usage & Feedback</p>
        </div>
      </header>

      <div class="admin-tabs">
        <button
          class={`admin-tab ${activeTab() === 'usage' ? 'active' : ''}`}
          onClick={() => handleTabChange('usage')}
        >
          Usage ({usageData().length})
        </button>
        <button
          class={`admin-tab ${activeTab() === 'feedback' ? 'active' : ''}`}
          onClick={() => handleTabChange('feedback')}
        >
          Feedback ({feedbackData().length})
        </button>
      </div>

      <Show when={error()}>
        <div class="admin-error">{error()}</div>
      </Show>

      <Show when={loading()}>
        <div class="admin-loading">Loading...</div>
      </Show>

      <Show when={!loading() && activeTab() === 'usage'}>
        <div class="admin-table-container">
          <table class="admin-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Fingerprint</th>
                <th>Requests</th>
                <th>First</th>
                <th>Last</th>
                <th>Location</th>
                <th>User Agent</th>
              </tr>
            </thead>
            <tbody>
              <For each={usageData()}>
                {(record) => (
                  <tr>
                    <td>{record.date}</td>
                    <td class="mono">{truncate(record.fingerprint, 12)}</td>
                    <td class="center">{record.request_count}</td>
                    <td>{formatDateTime(record.first_request_at)}</td>
                    <td>{formatDateTime(record.last_request_at)}</td>
                    <td>
                      {record.country || record.city 
                        ? `${record.city}${record.city && record.country ? ', ' : ''}${record.country}`
                        : '-'}
                    </td>
                    <td title={record.user_agent}>{truncate(record.user_agent, 30)}</td>
                  </tr>
                )}
              </For>
              <Show when={usageData().length === 0}>
                <tr>
                  <td colspan="7" class="center">No usage data yet</td>
                </tr>
              </Show>
            </tbody>
          </table>
        </div>
      </Show>

      <Show when={!loading() && activeTab() === 'feedback'}>
        <div class="admin-feedback-list">
          <For each={feedbackData()}>
            {(record) => (
              <div class="feedback-card">
                <div class="feedback-header">
                  <span 
                    class="feedback-type-badge"
                    style={{ background: getTypeColor(record.type) }}
                  >
                    {record.type}
                  </span>
                  <span class="feedback-date">{formatDateTime(record.created_at)}</span>
                </div>
                <div class="feedback-message">{record.message}</div>
                <Show when={record.contact}>
                  <div class="feedback-contact">
                    <strong>Contact:</strong>
                    {record.contact?.name && <span>{record.contact.name}</span>}
                    {record.contact?.email && <span>📧 {record.contact.email}</span>}
                    {record.contact?.phone && <span>📞 {record.contact.phone}</span>}
                    {record.contact?.company && <span>🏢 {record.contact.company}</span>}
                  </div>
                </Show>
                <div class="feedback-meta">
                  <span class="mono" title={record.fingerprint}>
                    {truncate(record.fingerprint, 12)}
                  </span>
                  {record.logs_url && (
                    <a href={record.logs_url} target="_blank" rel="noopener noreferrer">
                      View Logs
                    </a>
                  )}
                </div>
              </div>
            )}
          </For>
          <Show when={feedbackData().length === 0}>
            <div class="feedback-empty">No feedback submitted yet</div>
          </Show>
        </div>
      </Show>
    </div>
  );
};

export default AdminDashboard;
