# Copyright 2025 DataRobot, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app import Config


def test__config__load_env_vars() -> None:
    # mix of prefixed and unprefixed env vars
    env_vars = dict(
        DATAROBOT_ENDPOINT="https://api.test.datarobot.com",
        DATAROBOT_API_TOKEN="local-test-datarobot-api-key",
        LLM_DEPLOYMENT_ID="local-test-llm-deployment-id",
        # The format of secrets in the DataRobot Custom App env
        MLOPS_RUNTIME_PARAM_SESSION_SECRET_KEY='{"type":"credential","payload":{"credentialType":"api_token","apiToken":"test-secret-key"}}',
        MLOPS_RUNTIME_PARAM_DATAROBOT_OAUTH_PROVIDERS='["abc", "123"]',
    )

    with patch.dict(os.environ, env_vars, clear=True):
        config = Config()

        assert config.datarobot_endpoint == "https://api.test.datarobot.com"
        assert config.datarobot_api_token == "local-test-datarobot-api-key"
        assert config.session_secret_key == "test-secret-key"
        assert config.llm_deployment_id == "local-test-llm-deployment-id"
        assert config.datarobot_oauth_providers
        assert len(config.datarobot_oauth_providers) == 2
        # Semantic retrieval ships OFF by default (feature flag).
        assert config.vdb_enabled is False


def test__config__vdb_enabled_flag_parses() -> None:
    env_vars = dict(
        DATAROBOT_ENDPOINT="https://api.test.datarobot.com",
        DATAROBOT_API_TOKEN="x",
        MLOPS_RUNTIME_PARAM_SESSION_SECRET_KEY='{"type":"credential","payload":{"credentialType":"api_token","apiToken":"s"}}',
        VDB_ENABLED="true",
        MEMORY_SPACE_ID="space-123",
        CHAT_MEMORY_ENABLED="true",
    )
    with patch.dict(os.environ, env_vars, clear=True):
        config = Config()
        assert config.vdb_enabled is True
        assert config.memory_space_id == "space-123"
        assert config.chat_memory_enabled is True


def _base_env(**extra: str) -> dict[str, str]:
    env = dict(
        DATAROBOT_ENDPOINT="https://api.test.datarobot.com",
        DATAROBOT_API_TOKEN="x",
        MLOPS_RUNTIME_PARAM_SESSION_SECRET_KEY='{"type":"credential","payload":{"credentialType":"api_token","apiToken":"s"}}',
    )
    env.update(extra)
    return env


def test__config__rejects_overlap_at_or_above_chunk_size() -> None:
    """An overlap >= chunk size stalls the chunking window (one chunk per
    character), so it must fail loudly at startup rather than be clamped silently."""
    for overlap in ("1200", "5000"):
        with patch.dict(
            os.environ,
            _base_env(VDB_CHUNK_CHARS="1200", VDB_CHUNK_OVERLAP_CHARS=overlap),
            clear=True,
        ):
            with pytest.raises(ValidationError):
                Config()


def test__config__rejects_tiny_chunk_size() -> None:
    """A non-positive or absurdly small chunk size would explode the chunk count."""
    for chunk in ("0", "-100", "10"):
        with patch.dict(os.environ, _base_env(VDB_CHUNK_CHARS=chunk), clear=True):
            with pytest.raises(ValidationError):
                Config()


def test__config__accepts_sane_chunking() -> None:
    with patch.dict(
        os.environ,
        _base_env(VDB_CHUNK_CHARS="2000", VDB_CHUNK_OVERLAP_CHARS="150"),
        clear=True,
    ):
        config = Config()
        assert config.vdb_chunk_chars == 2000
        assert config.vdb_chunk_overlap_chars == 150
