/**
 * Agent configuration based on build-time environment variable.
 * 
 * Set VITE_AGENT=faa, VITE_AGENT=nrc, or VITE_AGENT=dod when building.
 * Defaults to 'faa' if not set.
 */

export type AgentType = 'faa' | 'nrc' | 'dod';

// Get agent from environment (build-time)
const agentEnv = import.meta.env.VITE_AGENT as string | undefined;
export const AGENT: AgentType = 
  (agentEnv === 'nrc') ? 'nrc' : 
  (agentEnv === 'dod') ? 'dod' : 
  'faa';

interface AgentBranding {
  name: string;
  shortName: string;
  title: string;
  subtitle: string;
  placeholder: string;
  welcomeTitle: string;
  welcomeText: string;
  primaryColor: string;
  logoText: string;
  sessionStoragePrefix: string;
}

interface AgentConfig {
  branding: AgentBranding;
  exampleQueries: string[];
}

const FAA_CONFIG: AgentConfig = {
  branding: {
    name: 'FAA Certification Agent',
    shortName: 'FAA Agent',
    title: 'FAA Certification Agent',
    subtitle: 'Aviation regulation assistance',
    placeholder: 'Ask about FAA regulations...',
    welcomeTitle: 'How can I help you today?',
    welcomeText: 'I can help you navigate FAA regulations, advisory circulars, and certification requirements. Ask me about specific CFR sections, compliance guidance, or certification topics.',
    primaryColor: '#1e40af',
    logoText: 'FAA',
    sessionStoragePrefix: 'faa',
  },
  exampleQueries: [
    "What are the stall speed requirements for transport aircraft?",
    "Explain HIRF protection requirements under Part 25",
    "What does §25.1309 say about equipment failure conditions?",
    "How do I demonstrate compliance with bird strike requirements?",
  ],
};

const NRC_CONFIG: AgentConfig = {
  branding: {
    name: 'NRC Regulatory Agent',
    shortName: 'NRC Agent',
    title: 'NRC Regulatory Agent',
    subtitle: 'Nuclear regulatory assistance',
    placeholder: 'Ask about NRC regulations...',
    welcomeTitle: 'How can I help you today?',
    welcomeText: 'I can help you navigate NRC regulations, regulatory guides, and nuclear licensing requirements. Ask me about specific CFR sections, NUREG reports, or compliance guidance.',
    primaryColor: '#166534',
    logoText: 'NRC',
    sessionStoragePrefix: 'nrc',
  },
  exampleQueries: [
    "What are the Part 21 reporting requirements?",
    "Explain the requirements for safety system design in 10 CFR 50",
    "What does NUREG-0800 say about fire protection?",
    "How do I demonstrate compliance with seismic qualification requirements?",
  ],
};

const DOD_CONFIG: AgentConfig = {
  branding: {
    name: 'DoD Contract Agent',
    shortName: 'DoD Agent',
    title: 'DoD Contract Agent',
    subtitle: 'Defense acquisition & compliance',
    placeholder: 'Ask about FAR, DFARS, or DoD requirements...',
    welcomeTitle: 'How can I help you today?',
    welcomeText: 'I can help you navigate FAR, DFARS, and DoD security requirements. Ask me about contract clauses, CMMC compliance, NISPOM requirements, or CUI handling.',
    primaryColor: '#B8860B',  // Dark goldenrod
    logoText: 'DoD',
    sessionStoragePrefix: 'dod',
  },
  exampleQueries: [
    "What are the DFARS 7012 cybersecurity requirements?",
    "Explain CMMC Level 2 requirements for CUI",
    "What does FAR 52.204-21 require for basic safeguarding?",
    "How do cost accounting standards apply to DoD contracts?",
  ],
};

const AGENT_CONFIGS: Record<AgentType, AgentConfig> = {
  faa: FAA_CONFIG,
  nrc: NRC_CONFIG,
  dod: DOD_CONFIG,
};

export const config = AGENT_CONFIGS[AGENT];
export const { branding, exampleQueries } = config;
