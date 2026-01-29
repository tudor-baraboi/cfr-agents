import { defineConfig, Plugin } from 'vite';
import solidPlugin from 'vite-plugin-solid';

// Agent-specific metadata for link previews
const AGENT_METADATA: Record<string, { title: string; description: string }> = {
  faa: {
    title: 'FAA Certification Agent',
    description: 'AI assistant for navigating FAA regulations, advisory circulars, and certification requirements.',
  },
  nrc: {
    title: 'NRC Regulatory Agent',
    description: 'AI assistant for navigating NRC regulations, regulatory guides, and nuclear licensing requirements.',
  },
  dod: {
    title: 'DoD Contract Agent',
    description: 'AI assistant for navigating FAR, DFARS, and DoD security and compliance requirements.',
  },
};

// Plugin to inject agent-specific metadata into index.html
function agentMetadataPlugin(): Plugin {
  const agent = process.env.VITE_AGENT || 'faa';
  const meta = AGENT_METADATA[agent] || AGENT_METADATA.faa;
  
  return {
    name: 'agent-metadata',
    transformIndexHtml(html) {
      return html
        .replace(/<title>.*<\/title>/, `<title>${meta.title}</title>`)
        .replace(
          '</head>',
          `    <meta name="description" content="${meta.description}" />
    <meta property="og:title" content="${meta.title}" />
    <meta property="og:description" content="${meta.description}" />
    <meta property="og:type" content="website" />
  </head>`
        );
    },
  };
}

export default defineConfig({
  plugins: [solidPlugin(), agentMetadataPlugin()],
  server: {
    port: 3000,
    proxy: {
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
      '/documents': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/auth': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/feedback': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    target: 'esnext',
  },
  // SPA fallback is default behavior in Vite
});
