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
import asyncio
import json
import logging
import threading
from textwrap import dedent
from typing import Any, Dict, Optional, Union

from crewai import LLM, Agent, Crew, Task
from crewai.events import crewai_event_bus
from crewai.events.types.task_events import TaskCompletedEvent, TaskStartedEvent
from datarobot_genai.core.agents.base import (
    InvokeReturn,
    extract_user_prompt_content,
    is_streaming,
)
from datarobot_genai.crewai.agent import (
    build_llm,
)
from datarobot_genai.crewai.base import CrewAIAgent
from datarobot_genai.crewai.events import CrewAIEventListener
from openai.types.chat import CompletionCreateParams

import models
from config import Config
from core.document_loader import SUPPORTED_FILE_TYPES
from tool import (
    DocumentReadTool,
    FileListTool,
    KnowledgeBaseContentTool,
    KnowledgeBaseSearchTool,
)

logger = logging.getLogger(__name__)


class MyAgent(CrewAIAgent):
    """MyAgent is a custom agent that uses CrewAI to plan, write, and edit content.
    It utilizes DataRobot's LLM Gateway or a specific deployment for language model interactions.
    This example illustrates 3 agents that handle content creation tasks, including planning, writing,
    and editing blog posts.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model: Optional[str] = None,
        verbose: Optional[Union[bool, str]] = True,
        timeout: Optional[int] = 300,
        **kwargs: Any,
    ):
        """Initializes the MyAgent class with API key, base URL, model, and verbosity settings.

        Args:
            api_key: Optional[str]: API key for authentication with DataRobot services.
                Defaults to None, in which case it will use the DATAROBOT_API_TOKEN environment variable.
            api_base: Optional[str]: Base URL for the DataRobot API.
                Defaults to None, in which case it will use the DATAROBOT_ENDPOINT environment variable.
            model: Optional[str]: The LLM model to use.
                Defaults to None.
            verbose: Optional[Union[bool, str]]: Whether to enable verbose logging.
                Accepts boolean or string values ("true"/"false"). Defaults to True.
            timeout: Optional[int]: How long to wait for the agent to respond.
                Defaults to 90 seconds.
            **kwargs: Any: Additional keyword arguments passed to the agent.
                Contains any parameters received in the CompletionCreateParams.

        Returns:
            None
        """
        super().__init__(
            api_key=api_key,
            api_base=api_base,
            model=model,
            verbose=verbose,
            timeout=timeout,
            **kwargs,
        )
        self.config = Config()
        self.default_model = self.config.llm_default_model
        self.event_listener = CrewAIEventListener()
        self.knowledge_base_files: Dict[str, dict[str, str]] = {}

    def llm(
        self,
        preferred_model: str | None = None,
        auto_model_override: bool = True,
    ) -> LLM:
        """Returns the LLM to use for a given model.

        If a `preferred_model` is provided, it will be used. Otherwise, the default model will be used.
        If auto_model_override is True, it will try and use the model specified in the request
        but automatically back out to the default model if the LLM Gateway is not configured

        Args:
            preferred_model: Optional[str]: The model to use. If none, it defaults to config.llm_default_model.
            auto_model_override: Optional[bool]: If True, it will try and use the model
                specified in the request but automatically back out if the LLM Gateway is
                not available.

        Returns:
            LLM: The model to use.
        """
        model = preferred_model or self.default_model
        if auto_model_override and not self.config.use_datarobot_llm_gateway:
            model = self.default_model
        if self.verbose:
            print(f"Using model: {model}")
        return build_llm(
            api_base=self.api_base,
            api_key=self.api_key,
            model=model,
            deployment_id=self.config.llm_deployment_id,
            timeout=self.timeout,
        )

    def make_kickoff_inputs(
        self, user_prompt_content: str | dict[str, Any]
    ) -> dict[str, Any]:
        """Map the user prompt into Crew kickoff inputs expected by tasks/agents."""
        if isinstance(user_prompt_content, dict):
            inputs: dict[str, Any] = user_prompt_content
        else:
            try:
                inputs = json.loads(user_prompt_content)
            except json.decoder.JSONDecodeError:
                inputs = {"topic": str(user_prompt_content)}
        if "question" not in inputs:
            if "message" in inputs:
                inputs["question"] = inputs["message"]
            elif "topic" in inputs:
                inputs["question"] = inputs["topic"]
        if base := inputs.get("knowledge_base"):
            self._extract_and_store_knowledge_base_content(base)
            if "topic" not in inputs and "description" in base:
                inputs["topic"] = base["description"]
        else:
            inputs["knowledge_base"] = ""

        return inputs

    @property
    def file_list_tool(self) -> FileListTool:
        return FileListTool()

    @property
    def document_read_tool(self) -> DocumentReadTool:
        return DocumentReadTool()

    @property
    def knowledge_base_content_tool(self) -> KnowledgeBaseContentTool:
        """Returns the KnowledgeBaseContentTool instance."""
        return KnowledgeBaseContentTool(knowledge_base=self.knowledge_base_files)

    @property
    def knowledge_base_search_tool(self) -> KnowledgeBaseSearchTool:
        """Returns the KnowledgeBaseSearchTool instance."""
        return KnowledgeBaseSearchTool(knowledge_base=self.knowledge_base_files)

    @property
    def agent_file_searcher(self) -> Agent:
        return Agent(
            role="Files Agent",
            goal='Find the most closely related filenames and their contents from a list of files on the topic: "{topic}" as it relates to the question: "{question}". Your services aren\'t needed if the document is in the question already.',
            backstory="You are an expert at searching and reading files for helpful information. You can identify the most relevant"
            "file from a list of files. You are given a list of files and a topic. ",
            allow_delegation=False,
            verbose=self.verbose,
            max_iter=3,
            llm=self.llm(
                preferred_model="datarobot/bedrock/anthropic.claude-sonnet-4-20250514-v1:0",
            ),
        )

    @property
    def task_file_search(self) -> Task:
        return Task(
            name="Searching files",
            description=dedent(
                """
                Find the most relevant files to "{topic}" and "{question}" from a list of files.
                You should always use your tools to determine what files are available.
                Your task is complete if no files are relevant.

                The chance that the files are relevant is quite low,
                so you should only select files if they are very clearly relevant.
                Please return only filenames that have extensions in the approved extension list.
                This extension list is: """
                + str(SUPPORTED_FILE_TYPES)
                + """.

                If no relevant files are found, return an empty array.
            """
            ).strip(),
            expected_output="A JSON object with an array of file paths",
            output_pydantic=models.FileSearchOutput,
            agent=self.agent_file_searcher,
            tools=[self.file_list_tool],
        )

    @property
    def task_write(self) -> Task:
        return Task(
            name="Reading content",
            description=dedent("""
                1. Read the contents of the files you are given.
                2. Think and understand deeply the contents of the file.
                3. Determine the best way to summarize this information in a concise and understandable way.
                4. Create a summary that answers the question, "{question}".
                5. Critical: Do not reproduce substantial portions or the full text of the documents. Provide a synthesized answer only.

                It is extremely critical that you do your best to answer this question.
                If no file was provided by the file searcher, state 'No file content available to answer the question.'
            """).strip(),
            expected_output="A well-written summary that answers the question in markdown format, or a clear statement if no file content is available.",
            agent=self.agent_file_searcher,
            tools=[self.document_read_tool],
        )

    @property
    def document_in_question_agent(self) -> Agent:
        """An agent that can be used to answer questions about a document."""
        return Agent(
            role="Document Agent",
            goal=dedent("""
                If the question: "{question}" contains the phrase:
                "Here are the relevant documents with each document separated by three dashes",
                then you should read the pages of the documents from the question and answer the question prior to that phrase.
            """).strip(),
            backstory=dedent("""
                You are an expert at reading documents and answering questions about them, and when the question includes a document,
                you'll know you should take action to respond to it.
            """).strip(),
            allow_delegation=False,
            max_iter=5,
            verbose=self.verbose,
            llm=self.llm(
                preferred_model="datarobot/azure/gpt-4o-2024-11-20",
            ),
        )

    @property
    def task_in_question_write(self) -> Task:
        return Task(
            name="Analyzing content",
            description=dedent("""
                1. Check if the "{question}" contains the phrase "Here is the relevant document with each page separated by three dashes:".
                2. If it does, separate the question from the document content.
                3. Think and understand deeply the contents of the document part of the question.
                4. Determine the best way to summarize this information in a concise and understandable way.
                5. Create a summary that answers the question part of "{question}".
                6. If the phrase is not found, respond with "No embedded document found in question."

                It is extremely critical that you do your best to answer this question.
            """).strip(),
            expected_output=(
                "A well-written brief answer in markdown format that answers the question using the embedded document, or a clear statement if no embedded document is found. "
                "It must not include a verbatim copy of the original document."
            ),
            agent=self.document_in_question_agent,
        )

    @property
    def knowledge_base_agent(self) -> Agent:
        """An agent that searches through knowledge base files and answers questions using their content."""
        return Agent(
            role="Knowledge Base Agent",
            goal=(
                "Given a knowledge base with files and limited content previews, first identify the most relevant files "
                'for answering the question: "{question}", then retrieve and analyze their full content to provide a comprehensive answer.'
            ),
            backstory=(
                "You are an expert at both analyzing file metadata and reading comprehensive document content. "
                "You can identify the most relevant files from knowledge base systems where full content isn't immediately available, "
                "and then synthesize information from multiple documents to provide accurate, well-sourced answers. "
                "You have a two-step process: first analyze file previews to select relevant files, then read their full content to answer questions."
            ),
            allow_delegation=True,
            verbose=self.verbose,
            max_iter=5,
            llm=self.llm(
                preferred_model="datarobot/vertex_ai/gemini-2.5-flash",
            ),
        )

    @property
    def task_knowledge_base_file_search(self) -> Task:
        return Task(
            name="Searching knowledge base",
            description=dedent("""
                Analyze the knowledge base `files` provided in this JSON:

                ``` {knowledge_base}```

                to identify which files are most relevant for answering the question: "{question}".
                If there is nothing in between the ``` and ``` symbols, respond with 'No knowledge base files available.'

                Look at file names, metadata, the topic "{topic}", and any content previews to make your determination.
                Select the most relevant files that would likely contain the information needed to answer the question.
                You select them by what is assigned the 'uuid' key in the knowledge base json list of files.

                DO NOT select any keys such as owner_uuid or project_uuid (these are not file UUIDs). Only the key 'uuid'.

                IMPORTANT: Format your response as a clear list of UUIDs, one per line, like:
                Selected UUIDs:
                - [actual-uuid-from-knowledge-base]
                - [actual-uuid-from-knowledge-base]

                Only use the actual UUIDs found in the provided knowledge base data.
            """).strip(),
            expected_output="A clearly formatted list of the most relevant file UUIDs from the knowledge base, with each UUID on its own line, or 'No knowledge base files available.'",
            output_pydantic=models.UUIDListOutput,
            agent=self.knowledge_base_agent,
        )

    @property
    def task_knowledge_base_content_answer(self) -> Task:
        return Task(
            name="Analyzing knowledge base",
            description=dedent("""
                IMPORTANT: You have previously identified relevant file UUIDs in your previous task output.
                You must carefully examine the context from your previous task to extract these UUIDs.
                CRITICAL: You MUST use your tool to get the content from those files

                Using your full content tool is expensive, so be sure to search first using the UUIDs you found,
                and then decide if you need to read the full content.

                Your task:
                1. Look at the output from your previous Knowledge Base File Search task
                2. Find any lines that start with '- ' followed by a UUID in standard format
                3. Extract ALL actual UUIDs from those lines (NOT the examples from instructions)
                4. Search the contents of those UUIDs using keywords and/or regex patterns from the question
                5. If you do not have UUIDs, use search to find them.
                5. Use the search results to determine which files are most relevant from the list of UUIDs
                6. Use the knowledge base content tool with the extracted UUIDs as a list if you think the search
                   results weren't sufficient to answer the question properly
                7. Read and understand the content deeply
                8. Create a comprehensive answer to the question: "{question}" on the topic "{topic}"

                CRITICAL INSTRUCTIONS:
                - Never call the tool with an empty list
                - Only call the tool with UUIDs you extracted from your previous output
                - Never call the Knowledge Base Content Tool more than once!!!
                - Ignore any example UUIDs from instructions or documentation
                - If no UUIDs were found in your previous output, respond that no relevant files were identified
            """).strip(),
            expected_output="A comprehensive, well-formatted markdown summary answering the question using the knowledge base content.",
            agent=self.knowledge_base_agent,
            tools=[self.knowledge_base_content_tool, self.knowledge_base_search_tool],
        )

    @property
    def finalizer_agent(self) -> Agent:
        """An agent that coordinates and finalizes the outputs from all other agents."""
        return Agent(
            role="Finalizer Agent",
            goal=(
                "Analyze the outputs from all previous agents and provide a single, coherent, well-formatted answer to the question: "
                '"{question}" from the topic: "{topic}"'
            ),
            backstory=(
                "You are an expert coordinator who takes the work from multiple specialized agents "
                "and creates a final, polished response. You can determine which agent provided the "
                "most relevant information and synthesize multiple sources when needed. "
                "You never output raw tool results, full documents, or incomplete information."
            ),
            max_iter=5,
            allow_delegation=False,
            verbose=self.verbose,
            llm=self.llm(
                preferred_model="datarobot/vertex_ai/gemini-2.5-flash",
            ),
        )

    @property
    def task_finalize_response(self) -> Task:
        return Task(
            name="Preparing response",
            description=dedent("""
                Analyze all the outputs from the previous agents and create a single, coherent answer to: "{question}".

                You have access to:
                1. File search results and file-based content analysis
                2. Embedded document analysis (if present in the question)
                3. Knowledge base search and content analysis

                Your job is to:
                1. Determine which agents found relevant information
                2. Synthesize the most relevant and accurate information
                3. Create a well-formatted, comprehensive response
                4. Ignore any 'not available' or 'not found' responses
                5. If multiple sources provide information, combine them intelligently
                6. If no sources provide useful information, clearly state that no relevant information was found

                Never output raw tool results, file paths, or technical details - only the final answer.
            """).strip(),
            expected_output="A single, well-formatted markdown response that directly answers the user's question using the most relevant information found by all agents.",
            agent=self.finalizer_agent,
        )

    @property
    def agents(self) -> list[Agent]:
        return [
            self.agent_file_searcher,
            self.document_in_question_agent,
            self.knowledge_base_agent,
            self.finalizer_agent,
        ]

    @property
    def tasks(self) -> list[Task]:
        return [
            self.task_file_search,
            self.task_write,
            self.task_in_question_write,
            self.task_knowledge_base_file_search,
            self.task_knowledge_base_content_answer,
            self.task_finalize_response,
        ]

    def build_crewai_workflow(self) -> Crew:
        return Crew(agents=self.agents, tasks=self.tasks, verbose=self.verbose)

    async def invoke(
        self, completion_create_params: CompletionCreateParams
    ) -> InvokeReturn:
        """Override invoke to emit task progress events during streaming."""
        user_prompt_content = extract_user_prompt_content(completion_create_params)
        logger.debug("Running agent with user prompt: %s", user_prompt_content)

        # Setup event listener if available
        if hasattr(self, "event_listener") and crewai_event_bus is not None:
            try:
                listener = getattr(self, "event_listener")
                setup_fn = getattr(listener, "setup_listeners", None)
                if callable(setup_fn):
                    setup_fn(crewai_event_bus)
            except Exception as e:
                logger.debug("Failed to setup event listener: %s", e)

        crew = self.build_crewai_workflow()

        if is_streaming(completion_create_params):
            return self._streaming_invoke(crew, user_prompt_content)

        crew_output = crew.kickoff(inputs=self.make_kickoff_inputs(user_prompt_content))
        return self._process_crew_output(crew_output)

    async def _streaming_invoke(
        self, crew: Crew, user_prompt_content: str
    ) -> InvokeReturn:
        """Run crew with streaming task progress."""
        loop = asyncio.get_running_loop()
        event_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        def on_task_started(source: Any, event: TaskStartedEvent) -> None:
            task_name = (
                event.task.name if event.task and event.task.name else None
            ) or "Task"
            agent_name = (
                event.task.agent.role if event.task and event.task.agent else None
            ) or "Agent"
            loop.call_soon_threadsafe(
                event_queue.put_nowait,
                {
                    "type": "task_started",
                    "task_name": task_name,
                    "agent_name": agent_name,
                },
            )

        def on_task_completed(source: Any, event: TaskCompletedEvent) -> None:
            task_name = (
                event.task.name if event.task and event.task.name else None
            ) or "Task"
            agent_name = (
                event.task.agent.role if event.task and event.task.agent else None
            ) or "Agent"
            loop.call_soon_threadsafe(
                event_queue.put_nowait,
                {
                    "type": "task_completed",
                    "task_name": task_name,
                    "agent_name": agent_name,
                },
            )

        crew_result: Any = None
        crew_error: Exception | None = None

        def run_crew() -> None:
            nonlocal crew_result, crew_error
            try:
                if crewai_event_bus is not None:
                    with crewai_event_bus.scoped_handlers():
                        crewai_event_bus.on(TaskStartedEvent)(on_task_started)
                        crewai_event_bus.on(TaskCompletedEvent)(on_task_completed)
                        crew_result = crew.kickoff(
                            inputs=self.make_kickoff_inputs(user_prompt_content)
                        )
                else:
                    # No event bus available, run without task progress events
                    crew_result = crew.kickoff(
                        inputs=self.make_kickoff_inputs(user_prompt_content)
                    )
            except Exception as e:
                logger.exception("Crew execution failed: %s", e)
                crew_error = e
            finally:
                loop.call_soon_threadsafe(event_queue.put_nowait, None)

        thread = threading.Thread(target=run_crew, daemon=True)
        thread.start()

        # Efficiently await events without polling
        empty_usage = {"completion_tokens": 0, "prompt_tokens": 0, "total_tokens": 0}
        while (event := await event_queue.get()) is not None:
            yield (json.dumps({"task_progress": event}), None, empty_usage)

        await asyncio.to_thread(thread.join)

        if crew_error:
            raise crew_error

        yield self._process_crew_output(crew_result)

    def _extract_and_store_knowledge_base_content(self, base: dict[str, Any]) -> None:
        """Extracts and stores the encoded content from knowledge base files."""
        for file_info in base["files"]:
            file_uuid = file_info["uuid"]
            if "encoded_content" in file_info:
                if not file_info["encoded_content"]:
                    # This shouldn't happen in prod, but if you don't have libreoffice installed,
                    # or persistence of the KB is missing it can happen.
                    continue
                self.knowledge_base_files[file_uuid] = file_info["encoded_content"]
                del file_info[
                    "encoded_content"
                ]  # Remove encoded_content from working inputs
                file_info["encoded_content"] = self.knowledge_base_files[file_uuid].get(
                    "1", ""
                )[:500]  # preview
