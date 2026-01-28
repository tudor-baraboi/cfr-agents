// Frontend logging service with upload capability

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

export interface LogEntry {
  timestamp: string;
  level: LogLevel;
  category: string;
  message: string;
  data?: unknown;
}

const MAX_LOG_ENTRIES = 1000;
const logs: LogEntry[] = [];

function createEntry(level: LogLevel, category: string, message: string, data?: unknown): LogEntry {
  return {
    timestamp: new Date().toISOString(),
    level,
    category,
    message,
    data: data !== undefined ? structuredClone(data) : undefined,
  };
}

function addLog(entry: LogEntry): void {
  logs.push(entry);
  // Trim old entries if we exceed max
  if (logs.length > MAX_LOG_ENTRIES) {
    logs.splice(0, logs.length - MAX_LOG_ENTRIES);
  }
  
  // Also log to console in development
  const consoleMethod = entry.level === 'error' ? console.error 
    : entry.level === 'warn' ? console.warn 
    : entry.level === 'debug' ? console.debug 
    : console.log;
  
  const prefix = `[${entry.category}]`;
  if (entry.data !== undefined) {
    consoleMethod(prefix, entry.message, entry.data);
  } else {
    consoleMethod(prefix, entry.message);
  }
}

export const logger = {
  debug(category: string, message: string, data?: unknown): void {
    addLog(createEntry('debug', category, message, data));
  },
  
  info(category: string, message: string, data?: unknown): void {
    addLog(createEntry('info', category, message, data));
  },
  
  warn(category: string, message: string, data?: unknown): void {
    addLog(createEntry('warn', category, message, data));
  },
  
  error(category: string, message: string, data?: unknown): void {
    addLog(createEntry('error', category, message, data));
  },
  
  getLogs(): LogEntry[] {
    return [...logs];
  },
  
  clear(): void {
    logs.length = 0;
  },
  
  async upload(apiUrl: string, token: string): Promise<{ success: boolean; message: string }> {
    if (logs.length === 0) {
      return { success: false, message: 'No logs to upload' };
    }
    
    try {
      const response = await fetch(`${apiUrl}/logs/upload`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          logs: logs,
          userAgent: navigator.userAgent,
          url: window.location.href,
          uploadedAt: new Date().toISOString(),
        }),
      });
      
      if (!response.ok) {
        const text = await response.text();
        return { success: false, message: `Upload failed: ${response.status} ${text}` };
      }
      
      const result = await response.json();
      return { success: true, message: result.message || 'Logs uploaded successfully' };
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      return { success: false, message: `Upload error: ${message}` };
    }
  },
};
