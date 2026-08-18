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
""" "
We provide a series of baked in tools here, but for more complex
workflows, better tools, search, etc. Check out
https://github.com/crewAIInc/crewAI-tools?tab=readme-ov-file
for several high quality tools ready to use!
"""

import json
import re
from pathlib import Path
from typing import Any, List, Optional, Type

from crewai.tools import BaseTool
from opentelemetry import trace
from pydantic import BaseModel, Field

from agent.core.document_loader import document_loader

static_docs_path = Path(__file__).parent / "static_docs"

_TOOL_RESULT_MAX_CHARS = 500


class FileListTool(BaseTool):
    name: str = "File List Tool"
    description: str = (
        "This tool will provide a list of all file names and their associated paths. "
        "You should always check to see if the file you are looking for can be found here. "
        "For future queries you should use the full file path instead of just the name to avoid ambiguity."
        "This tool takes no arguments."
    )

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    def _run(self) -> List[str] | str:
        _root_readme = static_docs_path / "README.md"
        files = [
            str(f)
            for f in static_docs_path.glob("**/*")
            if f.is_file() and f != _root_readme
        ]
        if not files:
            # Return (don't raise) so crewai treats it as a tool observation the
            # agent can act on, rather than a tool-usage error it retries (crewai
            # >=1.11 retries raised tool exceptions, which is slow and noisy).
            return (
                "No files found in the folder. Please verify that you have access to datasets "
                "and that your credentials are correct."
            )
        span = trace.get_current_span()
        span.set_attribute("gen_ai.tool.call.arguments", "{}")
        span.set_attribute("gen_ai.tool.call.result", json.dumps(files))
        # Return an empty list (not an error) when no sample documents exist, so the
        # agent cleanly reports "no files available" instead of raising — a raised
        # tool error otherwise gets surfaced to the manager, which may paper over it
        # by inventing content.
        return files


class DocumentReadToolSchema(BaseModel):
    file_path: str = Field(..., description="Mandatory file_path of the file")


class DocumentReadTool(BaseTool):
    name: str = "Read the contents of an file"
    description: str = (
        "A tool that reads the contents of a file. To use this tool, provide a 'file_path' "
        "parameter with the filename and or path of the file that should be read."
        "You will receive a dictionary of pages and their associated text."
    )
    args_schema: Type[BaseModel] = DocumentReadToolSchema
    file_path: Optional[str] = None

    def __init__(self, file_path: Optional[str] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.file_path = file_path

    def _run(
        self,
        **kwargs: Any,
    ) -> dict[int, str] | str:
        # Return (don't raise) error messages: crewai >=1.11 retries raised tool
        # exceptions (slow/noisy); a returned string is a clean observation the
        # agent can act on.
        file_path = kwargs.get("file_path", self.file_path)
        if not file_path:
            return "file_path is required but was not provided"

        span = trace.get_current_span()
        span.set_attribute(
            "gen_ai.tool.call.arguments", json.dumps({"file_path": file_path})
        )
        try:
            pages: dict[int, str] = document_loader.convert_document_to_text(file_path)
            result = json.dumps(pages)
            span.set_attribute(
                "gen_ai.tool.call.result", result[:_TOOL_RESULT_MAX_CHARS]
            )
            return pages
        except Exception as e:  # noqa: BLE001 - tool boundary: any read failure becomes an agent observation
            return (
                f"Could not read dataset with file_path '{file_path}'. Please verify that the file_path exists "
                f"and you have access to it. Error: {e}"
            )


class KnowledgeBaseContentToolSchema(BaseModel):
    file_uuids: list[str] = Field(
        ..., description="Mandatory list of file UUIDs to retrieve contents for"
    )


class KnowledgeBaseContentTool(BaseTool):
    name: str = "Get contents of a list of files from the Knowledge Base"
    description: str = (
        "This tool retrieves the full content of knowledge base files by their UUIDs. "
        "To use this tool, provide a list of file UUIDs (strings in the format like "
        "'44c6434a-7396-4b05-8ff1-bf1ab7f6000a'). Extract these UUIDs from the 'uuid' key "
        "in the knowledge base JSON input — never use owner_uuid or project_uuid. "
        "You will receive a dictionary where the keys are the file UUIDs and values are "
        "dictionaries of pages and their associated text. "
        "Example input: ['44c6434a-7396-4b05-8ff1-bf1ab7f6000a', '22b19e27-15b8-4238-98f4-d66571aa0c58']"
    )
    args_schema: Type[BaseModel] = KnowledgeBaseContentToolSchema
    knowledge_base: dict[str, dict[str, str]] = dict()

    def __init__(
        self, knowledge_base: dict[str, dict[str, str]] | None = None, **kwargs: Any
    ) -> None:
        """
        Initializes the KnowledgeBaseContentTool with a knowledge base.
        """
        super().__init__(**kwargs)
        # We want to keep the reference to the original dictionary if it is anything but None
        # so that it can get updated with new objects
        self.knowledge_base = knowledge_base if knowledge_base is not None else dict()

    def _run(self, file_uuids: list[str]) -> dict[str, dict[str, str]]:
        """Retrieve the full content of knowledge base files by their UUIDs."""
        span = trace.get_current_span()
        span.set_attribute(
            "gen_ai.tool.call.arguments", json.dumps({"file_uuids": file_uuids})
        )

        if not file_uuids:
            result = {
                "error": {
                    "1": "No file UUIDs provided. Please provide a list of file UUIDs to retrieve content. "
                    "You should get these from the Knowledge Base File Searcher's output."
                }
            }
            span.set_attribute(
                "gen_ai.tool.call.result", json.dumps(result)[:_TOOL_RESULT_MAX_CHARS]
            )
            return result

        content_subset: dict[str, dict[str, str]] = {}
        for file_uuid in file_uuids:
            if file_uuid in self.knowledge_base:
                content_subset[file_uuid] = self.knowledge_base[file_uuid]
            else:
                content_subset[file_uuid] = {
                    "1": f"Content not found for file UUID: {file_uuid}"
                }
        span.set_attribute(
            "gen_ai.tool.call.result",
            json.dumps(content_subset)[:_TOOL_RESULT_MAX_CHARS],
        )
        return content_subset


class KnowledgeBaseSearchToolSchema(BaseModel):
    keywords: Optional[List[str]] = Field(
        default=None, description="List of keywords to search for (case-insensitive)"
    )
    regex_pattern: Optional[str] = Field(
        default=None, description="Regex pattern to search for"
    )
    context_chars: int = Field(
        default=200,
        description="Number of characters before and after each match to include (default: 200)",
    )
    max_matches: int = Field(
        default=10,
        description="Maximum number of matches to return per file (default: 10)",
    )


class KnowledgeBaseSearchTool(BaseTool):
    name: str = "Knowledge Base Search Tool"
    description: str = (
        "A powerful tool that searches through knowledge base content using keywords and/or regex patterns. "
        "You can specify keywords (case-insensitive) or a regex pattern, or both. "
        "The tool returns matches with configurable context (characters before and after the match). "
        "Useful for finding specific information, patterns, or concepts within documents. "
        "Parameters: "
        "- keywords: List of words/phrases to search for "
        "- regex_pattern: Regular expression pattern to match "
        "- context_chars: Number of characters of context around matches (default: 200) "
        "- max_matches: Maximum matches to return per file (default: 10) "
        "Note: You must provide either keywords or regex_pattern (or both)."
    )
    args_schema: Type[BaseModel] = KnowledgeBaseSearchToolSchema
    knowledge_base: dict[str, dict[str, str]] = dict()
    semantic_chunks: Optional[List[dict[str, Any]]] = None

    def __init__(
        self,
        knowledge_base: dict[str, dict[str, str]] | None = None,
        semantic_chunks: Optional[List[dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> None:
        """
        Initializes the KnowledgeBaseSearchTool with a knowledge base.
        """
        super().__init__(**kwargs)
        # We want to keep the reference to the original dictionary if it is anything but None
        # so that it can get updated with new objects
        self.knowledge_base = knowledge_base if knowledge_base is not None else dict()
        self.semantic_chunks = semantic_chunks

    def _run(
        self,
        keywords: Optional[List[str]] = None,
        regex_pattern: Optional[str] = None,
        context_chars: int = 200,
        max_matches: int = 10,
    ) -> dict[str, Any]:
        """Search through knowledge base content using keywords and/or regex patterns."""
        span = trace.get_current_span()
        span.set_attribute(
            "gen_ai.tool.call.arguments",
            json.dumps({"keywords": keywords, "regex_pattern": regex_pattern}),
        )
        # Return pre-computed semantic chunks if available. An empty list means
        # semantic search produced no hits, so fall through to keyword search on
        # the raw files (consistent with the truthiness routing gate in
        # make_kickoff_inputs, which also treats [] as "no semantic chunks").
        if self.semantic_chunks:
            result: dict[str, Any] = {
                "search_mode": "semantic",
                "semantic_chunks": self.semantic_chunks,
                "note": (
                    "These are the most relevant excerpts from the knowledge base, "
                    "ranked by similarity to the question. Answer the user's question "
                    "using ONLY the text in 'semantic_chunks'. Do not use outside "
                    "knowledge or invent details. If the answer is not contained in "
                    "these excerpts, say the documents do not contain that information. "
                    "Do not call the content tool — these excerpts are the content."
                ),
            }
            span.set_attribute(
                "gen_ai.tool.call.result", json.dumps(result)[:_TOOL_RESULT_MAX_CHARS]
            )
            return result
        # Validate inputs
        if not keywords and not regex_pattern:
            return {
                "error": "You must provide either keywords or regex_pattern (or both) to search."
            }

        if context_chars < 0:
            context_chars = 0
        if max_matches <= 0:
            max_matches = 10

        results: dict[str, Any] = {
            "search_summary": {
                "keywords": keywords,
                "regex_pattern": regex_pattern,
                "context_chars": context_chars,
                "max_matches": max_matches,
                "total_files_searched": len(self.knowledge_base),
                "files_with_matches": 0,
            },
            "matches": {},
        }

        if not self.knowledge_base:
            results["error"] = "Knowledge base is empty or not loaded."
            return results

        # Compile regex pattern if provided
        compiled_regex = None
        if regex_pattern:
            try:
                compiled_regex = re.compile(regex_pattern, re.IGNORECASE | re.MULTILINE)
            except re.error as e:
                return {"error": f"Invalid regex pattern '{regex_pattern}': {e}"}

        # Search through each file in the knowledge base
        for file_uuid, pages in self.knowledge_base.items():
            file_matches: list[dict[str, Any]] = []

            # Combine all pages into a single text for searching
            full_text = ""
            page_boundaries = {}  # Track where each page starts
            current_pos = 0

            for page_num, page_content in pages.items():
                page_boundaries[current_pos] = page_num
                full_text += page_content + "\n"
                current_pos = len(full_text)

            # Search for keywords
            if keywords:
                for keyword in keywords:
                    if not keyword.strip():
                        continue

                    # Case-insensitive keyword search
                    keyword_pattern = re.escape(keyword.strip())
                    for match in re.finditer(keyword_pattern, full_text, re.IGNORECASE):
                        if len(file_matches) >= max_matches:
                            break

                        start_pos = max(0, match.start() - context_chars)
                        end_pos = min(len(full_text), match.end() + context_chars)
                        context = full_text[start_pos:end_pos]

                        # Find which page this match is on
                        page_num = self._find_page_number(
                            match.start(), page_boundaries
                        )

                        file_matches.append(
                            {
                                "type": "keyword",
                                "pattern": keyword,
                                "match": match.group(),
                                "context": context,
                                "page": page_num,
                                "start_pos": match.start(),
                                "end_pos": match.end(),
                            }
                        )

                    if len(file_matches) >= max_matches:
                        break

            # Search for regex patterns
            if compiled_regex and len(file_matches) < max_matches:
                for match in compiled_regex.finditer(full_text):
                    if len(file_matches) >= max_matches:
                        break

                    start_pos = max(0, match.start() - context_chars)
                    end_pos = min(len(full_text), match.end() + context_chars)
                    context = full_text[start_pos:end_pos]

                    # Find which page this match is on
                    page_num = self._find_page_number(match.start(), page_boundaries)

                    file_matches.append(
                        {
                            "type": "regex",
                            "pattern": regex_pattern,
                            "match": match.group(),
                            "context": context,
                            "page": page_num,
                            "start_pos": match.start(),
                            "end_pos": match.end(),
                        }
                    )

            # Add file results if matches found
            if file_matches:
                results["matches"][file_uuid] = {
                    "total_matches": len(file_matches),
                    "matches": file_matches,
                }
                if isinstance(results["search_summary"]["files_with_matches"], int):
                    results["search_summary"]["files_with_matches"] += 1

        span.set_attribute(
            "gen_ai.tool.call.result", json.dumps(results)[:_TOOL_RESULT_MAX_CHARS]
        )
        return results

    def _find_page_number(self, position: int, page_boundaries: dict[int, str]) -> str:
        """Find which page a given position falls on."""
        page_num = "1"  # Default to page 1
        for boundary_pos, page in page_boundaries.items():
            if position >= boundary_pos:
                page_num = page
            else:
                break
        return page_num
