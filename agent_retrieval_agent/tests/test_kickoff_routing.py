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
"""
Routing-gate tests for MyAgent.make_kickoff_inputs.

These guard the dynamic-VDB path: when the web layer sends pre-computed
``semantic_chunks`` it strips ``encoded_content`` from the files, so
``knowledge_base_files`` is empty. The Knowledge Base Agent (which owns the
KnowledgeBaseSearchTool that surfaces the semantic chunks) must still be
routed to — i.e. ``knowledge_base_available`` must be "true".
"""

from agent.myagent import MyAgent


def _bare_agent() -> MyAgent:
    """A MyAgent with only the attributes make_kickoff_inputs touches.

    Avoids the heavy CrewAIAgent / Config / LLM initialization.
    """
    agent = MyAgent.__new__(MyAgent)
    agent.knowledge_base_files = {}
    agent._semantic_chunks = []
    # `verbose` is now a read-only property backed by `_verbose` (base class
    # exposes it via a setter override), so set the backing attribute directly.
    agent._verbose = False
    return agent


def test_semantic_chunks_without_encoded_content_routes_to_kb_agent() -> None:
    """The VDB path: files have NO encoded_content but semantic_chunks present."""
    agent = _bare_agent()
    payload = {
        "message": "what is the refund policy",
        "knowledge_base": {
            "description": "policies",
            "files": [{"uuid": "abc"}],  # encoded_content stripped by chat layer
            "semantic_chunks": [
                {
                    "file_id": 1,
                    "page_num": 1,
                    "text": "Refunds within 30 days",
                    "score": 0.9,
                }
            ],
        },
    }
    inputs = agent.make_kickoff_inputs(payload)
    assert inputs["knowledge_base_available"] == "true"
    assert agent._semantic_chunks  # populated


def test_semantic_chunks_are_cache_safe_when_tool_built_first() -> None:
    """A search tool captured before make_kickoff_inputs must still observe chunks
    populated later: _semantic_chunks is mutated in place, never reassigned."""
    agent = _bare_agent()
    tool = agent.knowledge_base_search_tool  # built BEFORE kickoff inputs
    assert not tool.semantic_chunks  # empty so far
    agent.make_kickoff_inputs(
        {
            "message": "what is the refund policy",
            "knowledge_base": {
                "description": "policies",
                "files": [{"uuid": "abc"}],
                "semantic_chunks": [{"text": "Refunds within 30 days", "score": 0.9}],
            },
        }
    )
    # Same list object, so the previously-built tool now sees the chunks.
    assert tool.semantic_chunks
    assert tool.semantic_chunks[0]["text"] == "Refunds within 30 days"


def test_encoded_content_only_routes_to_kb_agent() -> None:
    """The legacy keyword path: encoded_content present, no semantic_chunks."""
    agent = _bare_agent()
    payload = {
        "message": "what is the refund policy",
        "knowledge_base": {
            "description": "policies",
            "files": [
                {"uuid": "abc", "encoded_content": {"1": "Refunds within 30 days"}}
            ],
        },
    }
    inputs = agent.make_kickoff_inputs(payload)
    assert inputs["knowledge_base_available"] == "true"
    assert agent.knowledge_base_files  # populated from encoded_content


def test_no_kb_content_does_not_route_to_kb_agent() -> None:
    """No encoded_content and no semantic_chunks -> KB agent skipped."""
    agent = _bare_agent()
    payload = {
        "message": "hello",
        "knowledge_base": {"description": "empty", "files": [{"uuid": "abc"}]},
    }
    inputs = agent.make_kickoff_inputs(payload)
    assert inputs["knowledge_base_available"] == "false"


def test_no_knowledge_base_key_is_false() -> None:
    """No knowledge_base at all -> false."""
    agent = _bare_agent()
    inputs = agent.make_kickoff_inputs({"message": "hello"})
    assert inputs["knowledge_base_available"] == "false"
