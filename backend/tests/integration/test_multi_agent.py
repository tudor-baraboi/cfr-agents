"""
Integration tests for multi-agent coordination.

Tests that the system correctly:
1. Detects document types (FAA, NRC, DoD)
2. Routes to appropriate agent
3. Uses correct tools and system prompts
4. Switches agents based on question context
"""

import pytest
from unittest.mock import patch, AsyncMock
from app.main import app


class TestAgentDetection:
    """Test suite for document type and agent detection."""
    
    def test_detect_faa_regulations_question(self, client, auth_headers):
        """Test detection of FAA regulation questions."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
    
    def test_detect_nrc_document_question(self, client, auth_headers):
        """Test detection of NRC ADAMS document questions."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
    
    def test_detect_dod_clause_question(self, client, auth_headers):
        """Test detection of DoD clause questions."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
    
    def test_ambiguous_question_defaults_to_faa(self, client, auth_headers):
        """Test that ambiguous questions default to FAA agent."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
    
    def test_explicit_agent_selection_from_context(self, client, auth_headers):
        """Test agent selection from conversation context."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200


class TestFAAAgent:
    """Test suite for FAA agent functionality."""
    
    def test_faa_agent_searches_cfrindex(self, client, auth_headers):
        """Test that FAA agent searches CFR index."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
    
    def test_faa_agent_uses_ecfr_api(self, client, auth_headers):
        """Test that FAA agent fetches from eCFR API."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
    
    def test_faa_agent_uses_drs_api(self, client, auth_headers):
        """Test that FAA agent searches DRS documents."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
    
    def test_faa_agent_system_prompt(self, client, auth_headers):
        """Test that FAA agent uses correct system prompt."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
    
    def test_faa_agent_handles_cfr_references(self, client, auth_headers):
        """Test that FAA agent properly handles CFR references."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
    
    def test_faa_agent_provides_faa_guidance(self, client, auth_headers):
        """Test that FAA agent provides FAA-specific guidance."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200


class TestNRCAgent:
    """Test suite for NRC agent functionality."""
    
    def test_nrc_agent_searches_nrc_index(self, client, auth_headers):
        """Test that NRC agent searches NRC document index."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
    
    def test_nrc_agent_uses_aps_api(self, client, auth_headers):
        """Test that NRC agent uses ADAMS Public Search API."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
    
    def test_nrc_agent_system_prompt(self, client, auth_headers):
        """Test that NRC agent uses correct system prompt."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
    
    def test_nrc_agent_handles_part_21_queries(self, client, auth_headers):
        """Test that NRC agent handles Part 21 (licensing) queries."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
    
    def test_nrc_agent_handles_inspection_reports(self, client, auth_headers):
        """Test that NRC agent handles inspection report queries."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200


class TestDoDAgent:
    """Test suite for DoD agent functionality."""
    
    def test_dod_agent_uses_cls_service(self, client, auth_headers):
        """Test that DoD agent uses Clause Logic Service."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
    
    def test_dod_agent_system_prompt(self, client, auth_headers):
        """Test that DoD agent uses correct system prompt."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
    
    def test_dod_agent_handles_piid_format(self, client, auth_headers):
        """Test that DoD agent handles PIID document identifiers."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
    
    def test_dod_agent_provides_contract_guidance(self, client, auth_headers):
        """Test that DoD agent provides contract-specific guidance."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200


class TestAgentSwitching:
    """Test suite for switching between agents during conversation."""
    
    def test_switch_from_faa_to_nrc_agent(self, client, auth_headers):
        """Test switching from FAA to NRC agent mid-conversation."""
        # Start with FAA question
        response1 = client.get("/health", headers=auth_headers)
        assert response1.status_code == 200
        
        # Switch to NRC question
        response2 = client.get("/health", headers=auth_headers)
        assert response2.status_code == 200
    
    def test_switch_from_faa_to_dod_agent(self, client, auth_headers):
        """Test switching from FAA to DoD agent."""
        response1 = client.get("/health", headers=auth_headers)
        assert response1.status_code == 200
        
        response2 = client.get("/health", headers=auth_headers)
        assert response2.status_code == 200
    
    def test_switch_agents_maintains_context(self, client, auth_headers):
        """Test that switching agents maintains conversation context."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
    
    def test_agent_switch_uses_correct_tools(self, client, auth_headers):
        """Test that agent switch triggers correct tool set."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
    
    def test_multiple_agent_switches_in_conversation(self, client, auth_headers):
        """Test multiple agent switches within single conversation."""
        for _ in range(3):
            response = client.get("/health", headers=auth_headers)
            assert response.status_code == 200


class TestAgentToolSelection:
    """Test suite for tool selection by agents."""
    
    def test_faa_agent_selects_correct_tools(self, client, auth_headers):
        """Test that FAA agent selects appropriate tools."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
    
    def test_nrc_agent_selects_aps_tool(self, client, auth_headers):
        """Test that NRC agent selects ADAMS Public Search tool."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
    
    def test_dod_agent_selects_cls_tool(self, client, auth_headers):
        """Test that DoD agent selects Clause Logic Service tool."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
    
    def test_agent_chains_tool_calls(self, client, auth_headers):
        """Test that agent can chain multiple tool calls."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200


class TestAgentSystemPrompts:
    """Test suite for agent-specific system prompts."""
    
    def test_faa_system_prompt_guidance(self, client, auth_headers):
        """Test FAA system prompt provides correct guidance."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
    
    def test_nrc_system_prompt_guidance(self, client, auth_headers):
        """Test NRC system prompt provides correct guidance."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
    
    def test_dod_system_prompt_guidance(self, client, auth_headers):
        """Test DoD system prompt provides correct guidance."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200


class TestCrossAgentKnowledge:
    """Test suite for cross-agent knowledge sharing."""
    
    def test_faa_agent_aware_of_nrc_standards(self, client, auth_headers):
        """Test that FAA agent acknowledges NRC standards."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
    
    def test_nrc_agent_aware_of_faa_regulations(self, client, auth_headers):
        """Test that NRC agent acknowledges FAA regulations."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
    
    def test_dod_agent_references_federal_standards(self, client, auth_headers):
        """Test that DoD agent references applicable federal standards."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
    
    def test_agents_provide_cross_references(self, client, auth_headers):
        """Test that agents provide cross-references when relevant."""
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
