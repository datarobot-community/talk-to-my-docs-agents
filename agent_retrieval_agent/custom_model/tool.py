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
from pathlib import Path
from typing import Any, List, Optional, Type

from core.document_loader import document_loader
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

sample_documents_path = Path(__file__).parent / "sample_documents"


class FileListTool(BaseTool):  # type: ignore[misc]
    name: str = "File List Tool"
    description: str = (
        "This tool will provide a list of all file names and their associated paths. "
        "You should always check to see if the file you are looking for can be found here. "
        "For future queries you should use the full file path instead of just the name to avoid ambiguity."
        "This tool takes no arguments."
    )

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    def _run(self) -> List[str]:
        files = [str(f) for f in sample_documents_path.glob("**/*") if f.is_file()]
        if not files:
            raise ValueError(
                "No files found in the folder. Please verify that you have access to datasets "
                "and that your credentials are correct."
            )
        return files


class DocumentReadToolSchema(BaseModel):
    file_path: str = Field(..., description="Mandatory file_path of the file")


class DocumentReadTool(BaseTool):  # type: ignore[misc]
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
    ) -> dict[int, str]:
        file_path = kwargs.get("file_path", self.file_path)
        if not file_path:
            raise ValueError("file_path is required but was not provided")

        try:
            pages: dict[int, str] = document_loader.convert_document_to_text(
                sample_documents_path / file_path
            )
            return pages
        except Exception as e:
            raise ValueError(
                f"Could not read dataset with file_path '{file_path}'. Please verify that the file_path exists "
                f"and you have access to it. Error: {e}"
            )


class KnowledgeBaseContentToolSchema(BaseModel):
    file_uuids: list[str] = Field(
        ..., description="Mandatory list of file UUIDs to retrieve contents for"
    )


class KnowledgeBaseContentTool(BaseTool):  # type: ignore[misc]
    name: str = "Get contents of a list of files from the Knowledge Base"
    description: str = (
        "This tool retrieves the full content of knowledge base files by their UUIDs. "
        "To use this tool, provide a list of file UUIDs (strings in the format like "
        "'44c6434a-7396-4b05-8ff1-bf1ab7f6000a'). You should get these UUIDs from the "
        "Knowledge Base File Searcher's output. "
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
        self.knowledge_base = knowledge_base or dict()

    def _run(self, file_uuids: list[str]) -> dict[str, dict[str, str]]:
        """Retrieve the full content of knowledge base files by their UUIDs."""
        if not file_uuids:
            return {
                "error": {
                    "1": "No file UUIDs provided. Please provide a list of file UUIDs to retrieve content. "
                    "You should get these from the Knowledge Base File Searcher's output."
                }
            }

        print(f"DEBUG: Received UUIDs: {file_uuids}", flush=True)
        print(
            f"DEBUG: Available knowledge base keys: {list(self.knowledge_base.keys())}",
            flush=True,
        )

        content_subset: dict[str, dict[str, str]] = {}
        for file_uuid in file_uuids:
            if file_uuid in self.knowledge_base:
                content_subset[file_uuid] = self.knowledge_base[file_uuid]
                print(f"DEBUG: Found content for UUID: {file_uuid}", flush=True)
            else:
                content_subset[file_uuid] = {
                    "1": f"Content not found for file UUID: {file_uuid}"
                }
                print(f"DEBUG: Content not found for UUID: {file_uuid}", flush=True)
        return content_subset
