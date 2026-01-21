# Copyright 2025 DataRobot, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import os
from unittest.mock import MagicMock, Mock, patch

import pytest
from agent import MyAgent
from ragas import MultiTurnSample
from ragas.messages import AIMessage, HumanMessage, ToolCall, ToolMessage


class TestMyAgentCrewAI:
    @pytest.fixture
    def agent(self):
        return MyAgent(api_key="test_key", api_base="test_base", verbose=True)

    def test_init_with_explicit_parameters(self):
        """Test initialization with explicitly provided parameters."""
        # Setup
        api_key = "test-api-key"
        api_base = "https://test-api-base.com"
        model = "test-model"
        verbose = True

        # Execute
        agent = MyAgent(
            api_key=api_key, api_base=api_base, model=model, verbose=verbose
        )

        # Assert
        assert agent.api_key == api_key
        assert agent.api_base == api_base
        assert agent.model == model
        assert agent.verbose is True

    @patch.dict(
        os.environ,
        {
            "DATAROBOT_API_TOKEN": "env-api-key",
            "DATAROBOT_ENDPOINT": "https://env-api-base.com",
        },
    )
    def test_init_with_environment_variables(self):
        """Test initialization using environment variables when no explicit parameters."""
        # Execute
        agent = MyAgent()

        # Assert
        assert agent.api_key == "env-api-key"
        assert agent.api_base == "https://env-api-base.com"
        assert agent.model is None
        assert agent.verbose is True

    @patch.dict(
        os.environ,
        {
            "DATAROBOT_API_TOKEN": "env-api-key",
            "DATAROBOT_ENDPOINT": "https://env-api-base.com",
        },
    )
    def test_init_explicit_params_override_env_vars(self):
        """Test explicit parameters override environment variables."""
        # Setup
        api_key = "explicit-api-key"
        api_base = "https://explicit-api-base.com"

        # Execute
        agent = MyAgent(api_key=api_key, api_base=api_base)

        # Assert
        assert agent.api_key == "explicit-api-key"
        assert agent.api_base == "https://explicit-api-base.com"

    def test_init_with_string_verbose_true(self):
        """Test initialization with string 'true' for verbose parameter."""
        # Setup
        verbose_values = ["true", "TRUE", "True"]

        for verbose in verbose_values:
            # Execute
            agent = MyAgent(verbose=verbose)

            # Assert
            assert agent.verbose is True

    def test_init_with_string_verbose_false(self):
        """Test initialization with string 'false' for verbose parameter."""
        # Setup
        verbose_values = ["false", "FALSE", "False"]

        for verbose in verbose_values:
            # Execute
            agent = MyAgent(verbose=verbose)

            # Assert
            assert agent.verbose is False

    def test_init_with_boolean_verbose(self):
        """Test initialization with boolean values for verbose parameter."""
        # Test with True
        agent = MyAgent(verbose=True)
        assert agent.verbose is True

        # Test with False
        agent = MyAgent(verbose=False)
        assert agent.verbose is False

    @patch.dict(os.environ, {}, clear=True)
    def test_init_with_additional_kwargs(self):
        """Test initialization with additional keyword arguments."""
        # Setup
        additional_kwargs = {"extra_param1": "value1", "extra_param2": 42}

        # Execute
        agent = MyAgent(**additional_kwargs)

        # Assert - Additional kwargs should be accepted but not stored as attributes
        assert agent.api_key is None  # Should fallback to env var or None
        assert agent.api_base == "https://app.datarobot.com"  # Default value
        assert agent.model is None
        assert agent.verbose is True

        # Verify that the extra parameters don't create attributes
        with pytest.raises(AttributeError):
            _ = agent.extra_param1

    @pytest.mark.parametrize(
        "api_base,expected_result",
        [
            ("https://example.com", "https://example.com/"),
            ("https://example.com/", "https://example.com/"),
            ("https://example.com/api/v2", "https://example.com/"),
            ("https://example.com/api/v2/", "https://example.com/"),
            ("https://example.com/other-path", "https://example.com/other-path/"),
            (
                "https://custom.example.com:8080/path/to/api/v2/",
                "https://custom.example.com:8080/path/to/",
            ),
            (
                "https://example.com/api/v2/deployment/",
                "https://example.com/api/v2/deployment/",
            ),
            (
                "https://example.com/api/v2/deployment",
                "https://example.com/api/v2/deployment/",
            ),
            (
                "https://example.com/api/v2/genai/llmgw/chat/completions",
                "https://example.com/api/v2/genai/llmgw/chat/completions",
            ),
            (
                "https://example.com/api/v2/genai/llmgw/chat/completions/",
                "https://example.com/api/v2/genai/llmgw/chat/completions",
            ),
            (None, "https://app.datarobot.com/"),
        ],
    )
    @patch("datarobot_genai.crewai.agent.LLM")
    def test_llm_gateway_with_api_base(self, mock_llm, api_base, expected_result):
        """Test api_base_litellm property with various URL formats."""
        with patch.dict(os.environ, {}, clear=True):
            agent = MyAgent(api_base=api_base)
            _ = agent.llm(preferred_model="datarobot/azure/gpt-5-mini-2025-08-07")
            mock_llm.assert_called_once_with(
                model="datarobot/azure/gpt-5-mini-2025-08-07",
                api_base=expected_result,
                api_key=None,
                timeout=300,
            )

    @pytest.mark.parametrize(
        "api_base,expected_result",
        [
            (
                "https://example.com",
                "https://example.com/api/v2/deployments/test-id/chat/completions",
            ),
            (
                "https://example.com/",
                "https://example.com/api/v2/deployments/test-id/chat/completions",
            ),
            (
                "https://example.com/api/v2/",
                "https://example.com/api/v2/deployments/test-id/chat/completions",
            ),
            (
                "https://example.com/api/v2",
                "https://example.com/api/v2/deployments/test-id/chat/completions",
            ),
            (
                "https://example.com/other-path",
                "https://example.com/other-path/api/v2/deployments/test-id/chat/completions",
            ),
            (
                "https://custom.example.com:8080/path/to",
                "https://custom.example.com:8080/path/to/api/v2/deployments/test-id/chat/completions",
            ),
            (
                "https://custom.example.com:8080/path/to/api/v2/",
                "https://custom.example.com:8080/path/to/api/v2/deployments/test-id/chat/completions",
            ),
            (
                "https://example.com/api/v2/deployments/",
                "https://example.com/api/v2/deployments/",
            ),
            (
                "https://example.com/api/v2/deployments",
                "https://example.com/api/v2/deployments/",
            ),
            (
                "https://example.com/api/v2/genai/llmgw/chat/completions",
                "https://example.com/api/v2/genai/llmgw/chat/completions",
            ),
            (
                "https://example.com/api/v2/genai/llmgw/chat/completions/",
                "https://example.com/api/v2/genai/llmgw/chat/completions",
            ),
            (
                None,
                "https://app.datarobot.com/api/v2/deployments/test-id/chat/completions",
            ),
        ],
    )
    @patch("datarobot_genai.crewai.agent.LLM")
    def test_llm_deployment_with_api_base(self, mock_llm, api_base, expected_result):
        """Test api_base_litellm property with various URL formats."""
        with patch.dict(os.environ, {"LLM_DEPLOYMENT_ID": "test-id"}, clear=True):
            agent = MyAgent(api_base=api_base)
            agent.config.llm_default_model = "datarobot/azure/gpt-5-mini-2025-08-07"
            _ = agent.llm(preferred_model="datarobot/azure/gpt-5-mini-2025-08-07")
            mock_llm.assert_called_once_with(
                model="datarobot/azure/gpt-5-mini-2025-08-07",
                api_base=expected_result,
                api_key=None,
                timeout=300,
            )

    @patch("datarobot_genai.crewai.agent.LLM")
    def test_llm(self, mock_llm, agent):
        # Test that LLM is created with correct parameters
        agent.llm()
        mock_llm.assert_called_once_with(
            model="datarobot/azure/gpt-5-mini-2025-08-07",
            api_base="test_base/",
            api_key="test_key",
            timeout=300,
        )

    @patch("datarobot_genai.crewai.agent.LLM")
    def test_llm_property_with_no_api_base(self, mock_llm, agent):
        # Test that LLM is created with correct parameters
        with patch.dict(os.environ, {}, clear=True):
            agent = MyAgent(api_key="test_key", verbose=True)
            agent.llm()
            mock_llm.assert_called_once_with(
                model="datarobot/azure/gpt-5-mini-2025-08-07",
                api_base="https://app.datarobot.com/",
                api_key="test_key",
                timeout=300,
            )

    @patch("datarobot_genai.crewai.base.Crew")
    @patch("agent.CrewAIEventListener")
    @patch("agent.Agent")
    def test_chat(
        self, mock_agent, mock_event_listener, mock_crew, agent, load_model_result
    ):
        # This test case covers testing that the agent invoke runs with the llm interactions mocked
        from custom import chat

        _ = mock_agent, agent  # Uncalled but left for global test setup

        crew_output = Mock(
            raw="agent result",
            token_usage=Mock(
                completion_tokens=1,
                prompt_tokens=2,
                total_tokens=3,
            ),
        )
        mock_crew.return_value = Mock(kickoff=MagicMock(return_value=crew_output))

        events = [
            HumanMessage(content="Hi"),
            AIMessage(
                content="Which language should I use?",
                tool_calls=[
                    ToolCall(name="find_language", args={"input_language": "en"})
                ],
            ),
            ToolMessage(content="Use en"),
            AIMessage(content="How are you today?"),
        ]
        mock_event_listener.return_value = Mock(messages=events)
        # Ensure the actual agent instance uses our mocked event listener
        agent.event_listener = mock_event_listener.return_value

        # Setup mocks
        completion_create_params = {
            "model": "test-model",
            "messages": [{"role": "user", "content": '{"topic": "test"}'}],
            "environment_var": True,
        }

        patches = []
        for method in dir(MyAgent):
            if method.startswith("task_"):
                patches.append(patch.object(MyAgent, method).__enter__())

        with (
            patch(
                "datarobot_genai.crewai.agent.create_pipeline_interactions_from_messages",
                return_value=MultiTurnSample(user_input=events),
            ),
        ):
            try:
                response = chat(
                    completion_create_params, load_model_result=load_model_result
                )
            finally:
                for p in patches:
                    p.__exit__()

        # Assert results - check the pipeline_interactions - other sections of the
        # results are already being checked in test_custom_model.py::test_chat
        completion = json.loads(response.model_dump_json())
        actual_events = json.loads(completion["pipeline_interactions"])["user_input"]
        for expected_message, actual_message in zip(events, actual_events):
            assert expected_message.content == actual_message["content"]
            assert expected_message.type == actual_message["type"]
