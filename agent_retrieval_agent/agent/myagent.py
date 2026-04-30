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
from crewai.events.types.logging_events import (
    AgentLogsExecutionEvent,
    AgentLogsStartedEvent,
)
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
from langchain_core.agents import AgentFinish
from openai.types.chat import CompletionCreateParams

from agent.config import Config
from agent.core.document_loader import EMBEDDED_DOCUMENTS_PHRASE, SUPPORTED_FILE_TYPES
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
                logger.warning(
                    "make_kickoff_inputs: failed to parse user_prompt_content as JSON "
                    "(type: %s), falling back to plain text. knowledge_base will not be available.",
                    type(user_prompt_content).__name__,
                )
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
            if not self.knowledge_base_files:
                logger.warning(
                    "make_kickoff_inputs: knowledge_base key present but no files with "
                    "encoded_content were extracted — routing will skip Knowledge Base Agent."
                )
        else:
            logger.info(
                "make_kickoff_inputs: no knowledge_base in inputs, routing to other Agents."
            )
        inputs["knowledge_base_available"] = (
            "true" if self.knowledge_base_files else "false"
        )
        logger.info(
            "make_kickoff_inputs: knowledge_base_available=%s",
            inputs["knowledge_base_available"],
        )

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
            goal=dedent(
                """
                Find the most closely related filenames and their contents from a list of files on the topic: "{topic}"
                as it relates to the question: "{question}".
                Only select files if they are very clearly relevant — the chance is quite low.
                Only return files with extensions in: """
                + str(SUPPORTED_FILE_TYPES)
                + dedent(""".
                If no relevant files are found, state that no file content is available.
                When reading file content, think deeply, summarize concisely, and provide a synthesized answer only.
                Do not reproduce substantial portions or the full text of documents.
            """)
            ).strip(),
            backstory=dedent("""
                You are an expert at searching and reading files for helpful information.
                You can identify the most relevant file from a list of files and summarize its contents accurately.
                You always use the file list tool first to see what is available, then read only the most relevant files.
            """).strip(),
            allow_delegation=False,
            verbose=self.verbose,
            max_iter=3,
            tools=[self.file_list_tool, self.document_read_tool]
            + list(self.tools or []),
            llm=self.llm(
                preferred_model="datarobot/bedrock/anthropic.claude-sonnet-4-20250514-v1:0",
            ),
        )

    @property
    def document_in_question_agent(self) -> Agent:
        return Agent(
            role="Document Agent",
            goal=dedent(
                """
                If the question: "{question}" contains the phrase:
                \""""
                + EMBEDDED_DOCUMENTS_PHRASE
                + dedent("""",
                separate the question from the document content, read the document pages, think deeply,
                and answer the question part concisely. Do not include a verbatim copy of the document in your answer.
            """)
            ).strip(),
            backstory=dedent("""
                You are an expert at reading documents and answering questions about them.
                When the question includes an embedded document, you carefully separate the question from the content,
                summarize concisely, and never reproduce the full document text.
                If the question does NOT contain the embedded document phrase, respond immediately:
                "No embedded document was provided. I cannot answer without one."
                Do not use any other knowledge or context to answer in that case.
            """).strip(),
            allow_delegation=False,
            max_iter=5,
            verbose=self.verbose,
            tools=list(self.tools or []),
            llm=self.llm(
                preferred_model="datarobot/azure/gpt-4o-2024-11-20",
            ),
        )

    @property
    def knowledge_base_agent(self) -> Agent:
        """An agent that searches through knowledge base files and answers questions using their content."""
        return Agent(
            role="Knowledge Base Agent",
            goal=dedent("""
                Given a knowledge base with files and limited content previews, first identify the most relevant files
                for answering the question: "{question}" on the topic: "{topic}",
                then retrieve and analyze their full content to provide a comprehensive answer.

                When selecting files, only use the 'uuid' key — never owner_uuid or project_uuid.
                Always search first using keywords or regex before fetching full content.
                Never call the content tool with an empty list.
                Never call the content tool more than once.
                If no UUIDs are found, respond that no relevant files were identified.
            """).strip(),
            backstory=dedent("""
                You are an expert at analyzing file metadata and reading comprehensive document content.
                You follow a strict two-step process: first use the search tool to find relevant content by UUID,
                then use the content tool only if the search results weren't sufficient to answer the question.
                You synthesize information accurately and never reproduce raw tool output.
            """).strip(),
            allow_delegation=False,
            verbose=self.verbose,
            max_iter=5,
            tools=[self.knowledge_base_content_tool, self.knowledge_base_search_tool]
            + list(self.tools or []),
            llm=self.llm(
                preferred_model="datarobot/vertex_ai/gemini-2.5-flash",
            ),
        )

    @property
    def manager_agent(self) -> Agent:
        """Coordinates specialist agents and synthesizes a final response."""
        return Agent(
            role="Manager Agent",
            goal=(
                "Analyze the outputs from all delegated agents and provide a single, coherent, well-formatted answer to the question: "
                '"{question}" from the topic: "{topic}"'
            ),
            backstory=(
                "You are an expert coordinator who takes the work from multiple specialized agents "
                "and creates a final, polished response. You can determine which agent provided the "
                "most relevant information and synthesize multiple sources when needed. "
                "You never output raw tool results, full documents, or incomplete information."
            ),
            max_iter=5,
            allow_delegation=True,
            verbose=self.verbose,
            llm=self.llm(
                preferred_model="datarobot/bedrock/anthropic.claude-sonnet-4-20250514-v1:0"
            ),
        )

    @property
    def task_answer_question(self) -> Task:
        return Task(
            name="Delegating question",
            description=dedent(
                """
                Answer the question: "{question}" on the topic: "{topic}".

                Determine the correct source and delegate to exactly one specialist:

                1. EMBEDDED DOCUMENT — if the question contains the phrase \""""
                + EMBEDDED_DOCUMENTS_PHRASE
                + dedent("""",
                   delegate to the Document Agent.

                2. KNOWLEDGE BASE — knowledge base available: {knowledge_base_available}.
                   If "true", delegate to the Knowledge Base Agent.

                3. SAMPLE FILES — if neither of the above applies,
                   delegate to the Files Agent to search for relevant local files.

                4. NO SOURCE — if no relevant content was found from any source,
                   state that no document source is available.

                After collecting the specialist's response:
                1. Determine if the agent answer matches the user prompt. If the agent returned an empty or failed response, retry the same specialist once. If still empty or not relevant, fall back through the priority chain: Knowledge Base Agent → Document Agent → Files Agent — stopping as soon as one returns a relevant answer.
                2. Synthesize the most relevant and accurate information
                3. Create a well-formatted, comprehensive response
                4. Ignore any 'not available' or 'not found' responses
                5. If multiple sources provide information, combine them intelligently
                6. If no sources provide useful information, clearly state that no relevant information was found

                Never output raw tool results, file paths, or technical details - only the final answer.
            """)
            ).strip(),
            expected_output="A single, well-formatted markdown response that directly answers the user's question using the most relevant information found by all agents.",
        )

    @property
    def agents(self) -> list[Agent]:
        return [
            self.document_in_question_agent,
            self.knowledge_base_agent,
            self.agent_file_searcher,
        ]

    @property
    def tasks(self) -> list[Task]:
        return [self.task_answer_question]

    def _extract_and_store_knowledge_base_content(self, base: dict[str, Any]) -> None:
        """Extracts and stores the encoded content from knowledge base files."""
        for file_info in base["files"]:
            file_uuid = file_info["uuid"]
            if "encoded_content" in file_info:
                if not file_info["encoded_content"]:
                    continue
                self.knowledge_base_files[file_uuid] = file_info["encoded_content"]
                del file_info["encoded_content"]

    def crew(self) -> Crew:
        """Override base class crew() to customize Crew options."""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            verbose=self.verbose,
            process=Process.hierarchical,
            manager_agent=self.manager_agent,
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

        agent_display_task: dict[str, str] = {
            "Document Agent": "Analyzing content",
            "Knowledge Base Agent": "Analyzing knowledge base",
            "Files Agent": "Analyzing files",
        }

        with crewai_event_bus.scoped_handlers():
            ragas_listener = CrewAIRagasEventListener()
            ragas_listener.setup_listeners(crewai_event_bus)

            @crewai_event_bus.on(CrewTaskStartedEvent)
            def _on_task_started(_: Any, event: Any) -> None:
                task = getattr(event, "task", None)
                agent = getattr(task, "agent", None)
                role = getattr(agent, "role", "") if agent else "Manager Agent"
                name = getattr(task, "name", "") or ""
                step_name = f"{role}: {name}" if role and name else role or name
                loop.call_soon_threadsafe(step_queue.put_nowait, ("start", step_name))

            @crewai_event_bus.on(CrewTaskCompletedEvent)
            def _on_task_completed(_: Any, event: Any) -> None:
                loop.call_soon_threadsafe(step_queue.put_nowait, ("end", ""))

            @crewai_event_bus.on(AgentLogsStartedEvent)
            def _on_agent_logs_started(_: Any, event: Any) -> None:
                role = getattr(event, "agent_role", "")
                if role == "Manager Agent":
                    return
                task_name = agent_display_task.get(role, "Working")
                loop.call_soon_threadsafe(
                    step_queue.put_nowait, ("start", f"{role}: {task_name}")
                )

            @crewai_event_bus.on(AgentLogsExecutionEvent)
            def _on_agent_logs_execution(_: Any, event: Any) -> None:
                role = getattr(event, "agent_role", "")
                if role == "Manager Agent":
                    return
                if not isinstance(
                    getattr(event, "formatted_answer", None), AgentFinish
                ):
                    return
                loop.call_soon_threadsafe(step_queue.put_nowait, ("end", ""))

            kickoff_inputs = self.make_kickoff_inputs(user_prompt_content)
            crew = self.crew()

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
