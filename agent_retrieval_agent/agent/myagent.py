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
import logging
import uuid
from textwrap import dedent
from typing import TYPE_CHECKING, Any, Optional

from ag_ui.core import (
    EventType,
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageChunkEvent,
)
from crewai import LLM, Agent, Crew, Process, Task
from crewai.events import TaskCompletedEvent as CrewTaskCompletedEvent
from crewai.events import TaskStartedEvent as CrewTaskStartedEvent
from crewai.events import crewai_event_bus
from crewai.tools import BaseTool
from datarobot_genai.core.agents import InvokeReturn
from datarobot_genai.core.agents.base import (
    UsageMetrics,
    default_usage_metrics,
    extract_user_prompt_content,
    prepare_identity_header,
)
from datarobot_genai.core.chat import agent_chat_completion_wrapper
from datarobot_genai.core.mcp import MCPConfig
from datarobot_genai.crewai.agent import CrewAIAgent
from datarobot_genai.crewai.mcp import mcp_tools_context
from datarobot_genai.crewai.ragas_events import CrewAIRagasEventListener
from openai.types.chat import CompletionCreateParams

import agent.models as models
from agent.config import Config
from agent.core.document_loader import SUPPORTED_FILE_TYPES
from agent.tool import (
    DocumentReadTool,
    FileListTool,
    KnowledgeBaseContentTool,
    KnowledgeBaseSearchTool,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ragas import MultiTurnSample


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
        verbose: bool = True,
        timeout: Optional[int] = 300,
        llm: Optional[LLM] = None,
        tools: Optional[list[BaseTool]] = None,
        forwarded_headers: Optional[dict[str, str]] = None,
    ):
        """Initializes the MyAgent class with API key, base URL, model, and verbosity settings.

        Args:
            api_key: Optional[str]: API key for authentication with DataRobot services.
                Defaults to None, in which case it will use the DATAROBOT_API_TOKEN environment variable.
            api_base: Optional[str]: Base URL for the DataRobot API.
                Defaults to None, in which case it will use the DATAROBOT_ENDPOINT environment variable.
            model: Optional[str]: The LLM model to use.
                Defaults to None.
            verbose: bool: Whether to enable verbose logging. Defaults to True.
            timeout: Optional[int]: How long to wait for the agent to respond.
                Defaults to 300 seconds.
            llm: Optional[LLM]: Pre-configured LLM instance provided by NAT.
                When set, llm() returns this directly instead of creating a new LLM.
            tools: Optional[list[BaseTool]]: Tools to use for the agent.
                Defaults to None.
            forwarded_headers: Optional[dict[str, str]]: Headers of the original request agent can use
                to access external services. Defaults to None.
        Returns:
            None
        """
        super().__init__(
            api_key=api_key,
            api_base=api_base,
            model=model,
            verbose=verbose,
            timeout=timeout,
            forwarded_headers=forwarded_headers,
            tools=tools,
        )
        self._llm = llm
        self.config = Config()
        self.default_model = self.config.llm_default_model
        self.knowledge_base_files: dict[str, dict[str, str]] = {}

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
        if self._llm is not None:
            return self._llm

        api_base = self.litellm_api_base(self.config.llm_deployment_id)
        model = preferred_model or self.model or self.default_model
        if auto_model_override and not self.config.use_datarobot_llm_gateway:
            model = self.default_model
        if self.verbose:
            print(f"Using model: {model}")

        config = {
            "model": model,
            "api_base": api_base,
            "api_key": self.api_key,
            "timeout": self.timeout,
        }

        if not self.config.use_datarobot_llm_gateway and self.forwarded_headers:
            identity_header = prepare_identity_header(self.forwarded_headers)
            if identity_header:
                config["extra_headers"] = identity_header  # type: ignore[assignment]

        return LLM(**config)  # type: ignore[arg-type]

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
            llm=self.llm(),
            tools=self.tools,
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
            llm=self.llm(),
            tools=self.tools,
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
            self.task_knowledge_base_content_answer,
            self.task_finalize_response,
        ]

    def _extract_and_store_knowledge_base_content(self, base: dict[str, Any]) -> None:
        """Extracts and stores the encoded content from knowledge base files."""
        for file_info in base["files"]:
            file_uuid = file_info["uuid"]
            if "encoded_content" in file_info:
                if not file_info["encoded_content"]:
                    continue
                self.knowledge_base_files[file_uuid] = file_info["encoded_content"]
                del file_info["encoded_content"]
                file_info["encoded_content"] = self.knowledge_base_files[file_uuid].get(
                    "1", ""
                )[:500]  # preview

    def crew(self) -> Crew:
        """Override base class crew() to customize Crew options."""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            verbose=self.verbose,
            process=Process.sequential,
            stream=False,
        )

    async def invoke(self, run_agent_input: Any) -> InvokeReturn:
        """Override to emit real-time task step events and handle non-streaming LLMs.

        The base class emits step events only when the LLM streams tokens. Many
        LLMs routed through DataRobot's LLM Gateway (Bedrock, Gemini) fall back to
        non-streaming, producing an empty response. This override:

        1. Runs the crew with stream=False for reliable text output.
        2. Listens to TaskStartedEvent / TaskCompletedEvent (fired regardless of
           LLM streaming) and yields StepStarted/StepFinished AG-UI events in
           near-real-time while the crew runs in a background asyncio Task.
        3. Emits the final text from crew_output.raw after execution completes.
        """
        loop = asyncio.get_running_loop()
        step_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

        user_prompt_content = extract_user_prompt_content(run_agent_input)
        thread_id = run_agent_input.thread_id
        run_id = run_agent_input.run_id
        zero: UsageMetrics = {
            "completion_tokens": 0,
            "prompt_tokens": 0,
            "total_tokens": 0,
        }

        yield (
            RunStartedEvent(
                type=EventType.RUN_STARTED, thread_id=thread_id, run_id=run_id
            ),
            None,
            default_usage_metrics(),
        )

        with crewai_event_bus.scoped_handlers():
            ragas_listener = CrewAIRagasEventListener()
            ragas_listener.setup_listeners(crewai_event_bus)

            @crewai_event_bus.on(CrewTaskStartedEvent)
            def _on_task_started(_: Any, event: Any) -> None:
                task = getattr(event, "task", None)
                agent = getattr(task, "agent", None)
                role = getattr(agent, "role", "") if agent else ""
                name = getattr(task, "name", "") or ""
                step_name = f"{role}: {name}" if role and name else role or name
                print(
                    f"[invoke] TaskStartedEvent fired: step_name={step_name!r}",
                    flush=True,
                )
                logger.info(f"[invoke] TaskStartedEvent fired: step_name={step_name!r}")
                loop.call_soon_threadsafe(step_queue.put_nowait, ("start", step_name))

            @crewai_event_bus.on(CrewTaskCompletedEvent)
            def _on_task_completed(_: Any, event: Any) -> None:
                logger.info("[invoke] TaskCompletedEvent fired")
                loop.call_soon_threadsafe(step_queue.put_nowait, ("end", ""))

            crew = self.crew()
            kickoff_inputs = self.make_kickoff_inputs(str(user_prompt_content))

            print("[invoke] Starting crew as background task", flush=True)
            logger.info("[invoke] Starting crew as background task")
            # Run crew as a background task so we can yield step events in real time
            crew_task: asyncio.Task[Any] = asyncio.ensure_future(
                crew.kickoff_async(inputs=kickoff_inputs)
            )

            current_step: str | None = None

            def _task_progress_chunk(
                task_name: str, agent_name: str, status: str
            ) -> tuple[TextMessageChunkEvent, None, UsageMetrics]:
                """Emit a task_progress JSON chunk consumed by the web app's TaskProgressProcessor."""
                payload = json.dumps(
                    {
                        "task_progress": {
                            "type": status,
                            "task_name": task_name,
                            "agent_name": agent_name,
                        }
                    }
                )
                return (
                    TextMessageChunkEvent(
                        type=EventType.TEXT_MESSAGE_CHUNK,
                        message_id=str(uuid.uuid4()),
                        delta=payload,
                    ),
                    None,
                    zero,
                )

            # Drain the step queue while the crew runs, yielding task_progress chunks
            while not crew_task.done():
                await asyncio.sleep(0.05)
                while not step_queue.empty():
                    action, step_name = step_queue.get_nowait()
                    logger.info(
                        f"[invoke] Draining step queue: action={action!r} step={step_name!r}"
                    )
                    if action == "start":
                        if current_step:
                            # Previous task completed (the TaskCompletedEvent may still be in queue)
                            parts = current_step.split(": ", 1)
                            yield _task_progress_chunk(
                                task_name=parts[1] if len(parts) == 2 else current_step,
                                agent_name=parts[0] if len(parts) == 2 else "",
                                status="task_completed",
                            )
                        current_step = step_name
                        parts = step_name.split(": ", 1)
                        yield _task_progress_chunk(
                            task_name=parts[1] if len(parts) == 2 else step_name,
                            agent_name=parts[0] if len(parts) == 2 else "",
                            status="task_started",
                        )
                    elif action == "end" and current_step:
                        parts = current_step.split(": ", 1)
                        yield _task_progress_chunk(
                            task_name=parts[1] if len(parts) == 2 else current_step,
                            agent_name=parts[0] if len(parts) == 2 else "",
                            status="task_completed",
                        )
                        current_step = None

            # Drain any events that arrived between the last sleep and task completion
            while not step_queue.empty():
                action, step_name = step_queue.get_nowait()
                if action == "start":
                    if current_step:
                        parts = current_step.split(": ", 1)
                        yield _task_progress_chunk(
                            task_name=parts[1] if len(parts) == 2 else current_step,
                            agent_name=parts[0] if len(parts) == 2 else "",
                            status="task_completed",
                        )
                    current_step = step_name
                    parts = step_name.split(": ", 1)
                    yield _task_progress_chunk(
                        task_name=parts[1] if len(parts) == 2 else step_name,
                        agent_name=parts[0] if len(parts) == 2 else "",
                        status="task_started",
                    )
                elif action == "end" and current_step:
                    parts = current_step.split(": ", 1)
                    yield _task_progress_chunk(
                        task_name=parts[1] if len(parts) == 2 else current_step,
                        agent_name=parts[0] if len(parts) == 2 else "",
                        status="task_completed",
                    )
                    current_step = None

            if current_step:
                parts = current_step.split(": ", 1)
                yield _task_progress_chunk(
                    task_name=parts[1] if len(parts) == 2 else current_step,
                    agent_name=parts[0] if len(parts) == 2 else "",
                    status="task_completed",
                )

            crew_output = await crew_task
            usage_metrics = self._extract_usage_metrics(crew_output)
            pipeline_interactions = self.create_pipeline_interactions_from_messages(
                ragas_listener.messages
            )

            response_text = str(crew_output.raw)
            if response_text:
                yield (
                    TextMessageChunkEvent(
                        type=EventType.TEXT_MESSAGE_CHUNK,
                        message_id=str(uuid.uuid4()),
                        delta=response_text,
                    ),
                    None,
                    usage_metrics,
                )

        yield (
            RunFinishedEvent(
                type=EventType.RUN_FINISHED, thread_id=thread_id, run_id=run_id
            ),
            pipeline_interactions,
            usage_metrics,
        )


async def custompy_adaptor(
    completion_create_params: CompletionCreateParams,
) -> InvokeReturn | tuple[str, Optional["MultiTurnSample"], UsageMetrics]:
    forwarded_headers = completion_create_params.get("forwarded_headers", {})
    authorization_context = completion_create_params.get("authorization_context", {})
    mcp_config = MCPConfig(
        forwarded_headers=forwarded_headers,
        authorization_context=authorization_context,
    )
    async with mcp_tools_context(mcp_config) as mcp_tools:
        agent = MyAgent(
            verbose=completion_create_params.get("verbose", True),  # type: ignore[arg-type]
            timeout=completion_create_params.get("timeout", 300),  # type: ignore[arg-type]
            tools=mcp_tools,
            forwarded_headers=forwarded_headers,  # type: ignore[arg-type]
        )
        return await agent_chat_completion_wrapper(agent, completion_create_params)
