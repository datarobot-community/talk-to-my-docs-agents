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

from unittest.mock import MagicMock, Mock, patch

import pytest

from custom import chat, load_model


@pytest.fixture(autouse=True)
def mock_agent():
    with patch("agent.myagent.MyAgent") as mock:

        async def gen():
            yield (
                "agent result",
                [],
                {"completion_tokens": 1, "prompt_tokens": 2, "total_tokens": 3},
            )

        mock_instance = MagicMock()
        mock_instance.invoke = Mock(return_value=gen())
        mock.return_value = mock_instance
        yield mock, mock_instance


@pytest.fixture
def mock_mcp_tools_context():
    with patch("agent.myagent.mcp_tools_context") as mock:
        yield mock


@pytest.fixture
def load_model_result():
    result = load_model("")
    yield result
    thread_pool_executor, event_loop = result
    thread_pool_executor.shutdown(wait=True)


@pytest.fixture
def completion_params():
    return {
        "model": "test-model",
        "messages": [{"role": "user", "content": '{"topic": "test"}'}],
    }


class TestAuthorizationContextPropagation:
    def test_authorization_context_set_in_params(
        self, mock_mcp_tools_context, load_model_result, completion_params
    ):
        auth_context = {"token": "test-token", "user_id": "test-user"}

        with patch("custom.resolve_authorization_context", return_value=auth_context):
            chat(completion_params, load_model_result)

        mcp_config = mock_mcp_tools_context.call_args[0][0]
        assert mcp_config.authorization_context == auth_context

    def test_authorization_context_passed_to_agent(
        self, mock_mcp_tools_context, load_model_result, completion_params
    ):
        auth_context = {"token": "test-token", "user_id": "test-user"}

        with patch("custom.resolve_authorization_context", return_value=auth_context):
            chat(completion_params, load_model_result)

        mock_mcp_tools_context.assert_called_once()
        mcp_config = mock_mcp_tools_context.call_args[0][0]
        assert mcp_config.authorization_context == auth_context

    def test_empty_authorization_context_handled(
        self, mock_mcp_tools_context, load_model_result, completion_params
    ):
        with patch("custom.resolve_authorization_context", return_value={}):
            response = chat(completion_params, load_model_result)

        assert response is not None
        mock_mcp_tools_context.assert_called_once()
        mcp_config = mock_mcp_tools_context.call_args[0][0]
        assert mcp_config.authorization_context == {}


class TestHeaderForwarding:
    def test_forwarded_headers_whitelisted(
        self, mock_mcp_tools_context, load_model_result, completion_params
    ):
        headers = {
            "x-datarobot-api-key": "secret-key",
            "x-datarobot-api-token": "secret-token",
            "x-custom-header": "should-be-filtered",
        }

        with patch("custom.resolve_authorization_context", return_value={}):
            chat(completion_params, load_model_result, headers=headers)

        mcp_config = mock_mcp_tools_context.call_args[0][0]
        forwarded = mcp_config.forwarded_headers
        assert forwarded["x-datarobot-api-key"] == "secret-key"
        assert forwarded["x-datarobot-api-token"] == "secret-token"
        assert "x-custom-header" not in forwarded

    def test_forwarded_headers_case_insensitive(
        self, mock_mcp_tools_context, load_model_result, completion_params
    ):
        header1 = "X-DataRobot-API-Key"
        header2 = "X-DATAROBOT-API-TOKEN"

        headers = {
            header1: "secret-key",
            header2: "secret-token",
        }

        with patch("custom.resolve_authorization_context", return_value={}):
            chat(completion_params, load_model_result, headers=headers)

        mcp_config = mock_mcp_tools_context.call_args[0][0]
        forwarded = mcp_config.forwarded_headers
        assert len(forwarded) == 2
        assert header1 in forwarded
        assert header2 in forwarded

    def test_forwarded_headers_empty_when_no_headers(
        self, mock_mcp_tools_context, load_model_result, completion_params
    ):
        with patch("custom.resolve_authorization_context", return_value={}):
            chat(completion_params, load_model_result)

        mcp_config = mock_mcp_tools_context.call_args[0][0]
        assert mcp_config.forwarded_headers == {}

    def test_forwarded_headers_empty_when_none(
        self, mock_mcp_tools_context, load_model_result, completion_params
    ):
        with patch("custom.resolve_authorization_context", return_value={}):
            chat(completion_params, load_model_result, headers=None)

        mcp_config = mock_mcp_tools_context.call_args[0][0]
        assert mcp_config.forwarded_headers == {}

    def test_only_whitelisted_headers_forwarded(
        self, mock_mcp_tools_context, load_model_result, completion_params
    ):
        headers = {
            "Authorization": "Bearer token",
            "Content-Type": "application/json",
            "X-Custom": "value",
        }

        with patch("custom.resolve_authorization_context", return_value={}):
            chat(completion_params, load_model_result, headers=headers)

        mcp_config = mock_mcp_tools_context.call_args[0][0]
        forwarded = mcp_config.forwarded_headers
        assert len(forwarded) == 0
