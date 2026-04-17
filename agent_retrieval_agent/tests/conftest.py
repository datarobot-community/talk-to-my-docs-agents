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
from concurrent.futures import ThreadPoolExecutor

import pytest
from ag_ui.core import (
    EventType,
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageChunkEvent,
)


@pytest.fixture
def mock_agent_response():
    """
    Fixture to return a mock agent response based on the agent template framework.
    """
    usage = {"completion_tokens": 1, "prompt_tokens": 2, "total_tokens": 3}
    zero = {"completion_tokens": 0, "prompt_tokens": 0, "total_tokens": 0}

    async def generate_response():
        yield (
            RunStartedEvent(
                type=EventType.RUN_STARTED, thread_id="test-thread", run_id="test-run"
            ),
            None,
            zero,
        )
        yield (
            TextMessageChunkEvent(
                type=EventType.TEXT_MESSAGE_CHUNK,
                message_id="test-msg",
                delta="agent result",
            ),
            None,
            usage,
        )
        yield (
            RunFinishedEvent(
                type=EventType.RUN_FINISHED, thread_id="test-thread", run_id="test-run"
            ),
            [],
            usage,
        )

    return generate_response()


@pytest.fixture()
def load_model_result():
    with ThreadPoolExecutor(1) as thread_pool_executor:
        event_loop = asyncio.new_event_loop()
        thread_pool_executor.submit(asyncio.set_event_loop, event_loop).result()
        yield (thread_pool_executor, event_loop)
