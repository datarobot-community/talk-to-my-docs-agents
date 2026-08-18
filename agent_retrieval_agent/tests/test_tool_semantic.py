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

from agent.tool import KnowledgeBaseSearchTool


class TestKnowledgeBaseSearchToolSemantic:
    def test_semantic_chunks_returned_directly(self) -> None:
        """When semantic_chunks are provided, _run returns them without keyword search."""
        chunks = [
            {"text": "The sky is blue.", "score": 0.95},
            {"text": "Water is H2O.", "score": 0.88},
        ]
        tool = KnowledgeBaseSearchTool(semantic_chunks=chunks)
        result = tool._run(keywords=["sky"])
        assert "semantic_chunks" in result
        assert len(result["semantic_chunks"]) == 2
        assert result["semantic_chunks"][0]["text"] == "The sky is blue."
        assert result["search_mode"] == "semantic"

    def test_no_semantic_chunks_falls_back_to_keyword_search(self) -> None:
        """When semantic_chunks is None, _run falls back to keyword/regex search."""
        knowledge_base = {
            "file-uuid-1": {"1": "The sky is blue and beautiful."},
        }
        tool = KnowledgeBaseSearchTool(
            knowledge_base=knowledge_base, semantic_chunks=None
        )
        result = tool._run(keywords=["sky"])
        assert "matches" in result
        assert "file-uuid-1" in result["matches"]

    def test_empty_semantic_chunks_falls_back_to_keyword_search(self) -> None:
        """An empty semantic_chunks list (no hits) must fall back to keyword search
        rather than returning an empty semantic result."""
        knowledge_base = {
            "file-uuid-1": {"1": "The sky is blue and beautiful."},
        }
        tool = KnowledgeBaseSearchTool(
            knowledge_base=knowledge_base, semantic_chunks=[]
        )
        result = tool._run(keywords=["sky"])
        assert result.get("search_mode") != "semantic"
        assert "matches" in result
        assert "file-uuid-1" in result["matches"]
