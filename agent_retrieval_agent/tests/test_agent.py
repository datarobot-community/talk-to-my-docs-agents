# Copyright 2026 DataRobot, Inc.
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

import asyncio
import json
import os
from unittest.mock import ANY, AsyncMock, Mock, patch

import pytest
from crewai.types.streaming import CrewStreamingOutput, StreamChunk, StreamChunkType
from datarobot_dome.guards.agent_goal_accuracy import (
    AIMessage,
    HumanMessage,
    ToolCall,
    ToolMessage,
)

from agent import MyAgent


def _streaming_output(chunks, result):
    """Build a CrewStreamingOutput that async-yields ``chunks`` then exposes ``result``.

    Mirrors crewai 1.11: ``crew.akickoff(stream=True)`` returns a
    ``CrewStreamingOutput`` whose async iterator drives execution and whose
    ``.result`` is the final ``CrewOutput`` once iteration completes.
    """

    async def _aiter():
        for chunk in chunks:
            yield chunk

    out = CrewStreamingOutput(async_iterator=_aiter())
    out._set_result(result)
    return out


def _text_chunk(content, agent_role):
    return StreamChunk(
        content=content,
        chunk_type=StreamChunkType.TEXT,
        agent_role=agent_role,
    )


class TestMyAgentCrewAI:
    @pytest.fixture
    def agent(self):
        return MyAgent(
            api_key="test_key",
            api_base="test_base",
            verbose=True,
            model="datarobot/azure/gpt-5-mini-2025-08-07",
        )

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
    @patch("agent.myagent.LLM")
    def test_llm_gateway_with_api_base(self, mock_llm, api_base, expected_result):
        """Test api_base_litellm property with various URL formats."""
        with patch.dict(os.environ, {}, clear=True):
            agent = MyAgent(
                api_base=api_base, model="datarobot/azure/gpt-5-mini-2025-08-07"
            )
            agent.config.llm_deployment_id = None
            _ = agent.llm()
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
    @patch("agent.myagent.LLM")
    def test_llm_deployment_with_api_base(self, mock_llm, api_base, expected_result):
        """Test api_base_litellm property with various URL formats."""
        with patch.dict(os.environ, {"LLM_DEPLOYMENT_ID": "test-id"}, clear=True):
            agent = MyAgent(api_base=api_base)
            agent.config.llm_default_model = "datarobot/azure/gpt-5-mini-2025-08-07"
            _ = agent.llm()
            mock_llm.assert_called_once_with(
                model="datarobot/azure/gpt-5-mini-2025-08-07",
                api_base=expected_result,
                api_key=None,
                timeout=300,
            )

    @patch("agent.myagent.LLM")
    def test_llm(self, mock_llm, agent):
        # Test that LLM is created with correct parameters
        agent.config.llm_deployment_id = None
        agent.llm()
        mock_llm.assert_called_once_with(
            model="datarobot/azure/gpt-5-mini-2025-08-07",
            api_base="test_base/",
            api_key="test_key",
            timeout=300,
        )

    @patch("agent.myagent.LLM")
    def test_llm_property_with_no_api_base(self, mock_llm, agent):
        # Test that LLM is created with correct parameters
        with patch.dict(os.environ, {}, clear=True):
            agent = MyAgent(
                api_key="test_key",
                verbose=True,
                model="datarobot/azure/gpt-5-mini-2025-08-07",
            )
            agent.config.llm_deployment_id = None
            agent.llm()
            mock_llm.assert_called_once_with(
                model="datarobot/azure/gpt-5-mini-2025-08-07",
                api_base="https://app.datarobot.com/",
                api_key="test_key",
                timeout=300,
            )

    @patch("agent.myagent.LLM")
    @pytest.mark.parametrize("use_datarobot_llm_gateway", [True, False])
    def test_llm_with_identity_token(self, mock_llm, use_datarobot_llm_gateway):
        with patch.dict(os.environ, {"LLM_DEPLOYMENT_ID": "test-id"}, clear=True):
            agent = MyAgent(
                api_key="test_key",
                verbose=True,
                model="datarobot/azure/gpt-5-mini-2025-08-07",
                forwarded_headers={
                    "x-datarobot-api-key": "abc",
                    "x-datarobot-identity-token": "xyz",
                },
            )
            agent.config.use_datarobot_llm_gateway = use_datarobot_llm_gateway
            agent.llm()

            if use_datarobot_llm_gateway:
                mock_llm.assert_called_once_with(
                    model="datarobot/azure/gpt-5-mini-2025-08-07",
                    api_base="https://app.datarobot.com/api/v2/deployments/test-id/chat/completions",
                    api_key="test_key",
                    timeout=300,
                )
            else:
                mock_llm.assert_called_once_with(
                    model="datarobot/azure/gpt-5-mini-2025-08-07",
                    api_base="https://app.datarobot.com/api/v2/deployments/test-id/chat/completions",
                    api_key="test_key",
                    timeout=300,
                    extra_headers={"X-DataRobot-Identity-Token": "xyz"},
                )

    @patch("agent.myagent.Agent")
    def test_agent_file_searcher_property(self, mock_agent, agent):
        mock_llm = Mock()
        with patch.object(MyAgent, "llm", return_value=mock_llm):
            agent.agent_file_searcher
            mock_agent.assert_called_once_with(
                role="Files Agent",
                goal=ANY,
                backstory=ANY,
                allow_delegation=False,
                verbose=True,
                max_iter=3,
                tools=ANY,
                llm=ANY,
            )

    @patch("agent.myagent.Agent")
    def test_document_in_question_agent_property(self, mock_agent, agent):
        mock_llm = Mock()
        with patch.object(MyAgent, "llm", return_value=mock_llm):
            agent.document_in_question_agent
            mock_agent.assert_called_once_with(
                role="Document Agent",
                goal=ANY,
                backstory=ANY,
                allow_delegation=False,
                verbose=True,
                max_iter=5,
                tools=ANY,
                llm=ANY,
            )

    @patch("agent.myagent.Agent")
    def test_knowledge_base_agent_property(self, mock_agent, agent):
        mock_llm = Mock()
        with patch.object(MyAgent, "llm", return_value=mock_llm):
            agent.knowledge_base_agent
            mock_agent.assert_called_once_with(
                role="Knowledge Base Agent",
                goal=ANY,
                backstory=ANY,
                allow_delegation=False,
                verbose=True,
                max_iter=5,
                tools=ANY,
                llm=ANY,
            )

    @patch("agent.myagent.Agent")
    def test_manager_agent_property(self, mock_agent, agent):
        mock_llm = Mock()
        with patch.object(MyAgent, "llm", return_value=mock_llm):
            agent.manager_agent
            mock_agent.assert_called_once_with(
                role=ANY,
                goal=ANY,
                backstory=ANY,
                allow_delegation=True,
                verbose=True,
                max_iter=5,
                llm=ANY,
            )

    @patch("agent.myagent.Task")
    def test_task_answer_question_property(self, mock_task, agent):
        agent.task_answer_question
        mock_task.assert_called_once_with(
            name="Delegating question",
            description=ANY,
            expected_output=ANY,
        )

    @patch("agent.myagent.Crew")
    @patch("agent.myagent.CrewAIModerationsEventListener")
    @patch("agent.myagent.trace.get_current_span")
    @patch("agent.myagent.Task")
    @patch("agent.myagent.Agent")
    def test_chat(
        self,
        mock_agent,
        mock_task,
        mock_get_current_span,
        mock_event_listener,
        mock_crew,
        agent,
        load_model_result,
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
        # invoke() runs the crew with stream=True via akickoff (-> CrewStreamingOutput),
        # async-iterates the manager's streamed answer (gated on "Final Answer:"), and
        # reads usage/.raw from streaming_output.result.
        streaming_output = _streaming_output(
            [_text_chunk("Final Answer: agent result", "Manager Agent")],
            crew_output,
        )
        mock_crew.return_value = Mock(akickoff=AsyncMock(return_value=streaming_output))
        mock_span = Mock()
        mock_span.is_recording.return_value = True
        mock_get_current_span.return_value = mock_span

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

        # Setup mocks
        completion_create_params = {
            "model": "test-model",
            "messages": [{"role": "user", "content": '{"topic": "test"}'}],
            "environment_var": True,
        }

        response = chat(completion_create_params, load_model_result=load_model_result)

        # Assert results - check the pipeline_interactions - other sections of the
        # results are already being checked in test_custom_model.py::test_chat
        completion = json.loads(response.model_dump_json())
        actual_events = json.loads(completion["pipeline_interactions"])["user_input"]
        for expected_message, actual_message in zip(events, actual_events):
            assert expected_message.content == actual_message["content"]
            assert expected_message.type == actual_message["type"]

        mock_span.set_attribute.assert_any_call("gen_ai.usage.input_tokens", 2)
        mock_span.set_attribute.assert_any_call("gen_ai.usage.output_tokens", 1)

    @patch("agent.myagent.Crew")
    @patch("agent.myagent.CrewAIModerationsEventListener")
    @patch("agent.myagent.trace.get_current_span")
    @patch("agent.myagent.Task")
    @patch("agent.myagent.Agent")
    def test_invoke_emits_final_answer(
        self,
        mock_agent,
        mock_task,
        mock_get_current_span,
        mock_event_listener,
        mock_crew,
        agent,
    ):
        """invoke() runs the crew via akickoff and emits the final answer from
        crew_output.raw as a single AG-UI text chunk, bracketed by
        RunStarted/RunFinished. Driven on a self-contained event loop (not
        pytest-asyncio) so it doesn't perturb other tests' current-loop state.
        """
        _ = mock_agent, mock_task

        crew_output = Mock(
            raw="final answer",
            token_usage=Mock(completion_tokens=1, prompt_tokens=2, total_tokens=3),
        )
        mock_crew.return_value = Mock(akickoff=AsyncMock(return_value=crew_output))
        mock_get_current_span.return_value = Mock(is_recording=Mock(return_value=False))
        mock_event_listener.return_value = Mock(messages=None)

        user_msg = Mock(role="user")
        user_msg.content = '{"topic": "docs", "question": "summarize"}'
        run_input = Mock(thread_id="t", run_id="r", messages=[user_msg])

        async def _collect() -> list:
            return [event async for event in agent.invoke(run_input)]

        loop = asyncio.new_event_loop()
        try:
            events = loop.run_until_complete(_collect())
        finally:
            loop.close()

        event_types = [type(event).__name__ for event, _pi, _um in events]
        assert event_types == [
            "RunStartedEvent",
            "TextMessageChunkEvent",
            "RunFinishedEvent",
        ]
        assert events[1][0].delta == "final answer"
