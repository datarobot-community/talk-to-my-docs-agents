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
import json
import logging
import uuid
from textwrap import dedent
from typing import TYPE_CHECKING, Any, Optional, cast

from ag_ui.core import (
    EventType,
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageChunkEvent,
)
from crewai import LLM, Agent, Crew, Process, Task
from crewai.events import (
    crewai_event_bus,
)
from crewai.tools import BaseTool
from crewai.types.streaming import CrewStreamingOutput, StreamChunkType
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
from opentelemetry import trace

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
        timeout: int = 300,
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
        self._crew: Optional[Crew] = None

    # The datarobot-genai CrewAIAgent base eagerly mutates a *cached* set of crew
    # agents in these setters (and calls them during __init__, before all state is
    # set). MyAgent instead builds its agents/crew lazily in the cached `crew`
    # property, reading these values plus per-agent tools (`+ self.tools`) and
    # per-agent model selection (`self.llm(preferred_model=...)`). So we override
    # the setters to simply store the value and skip the base's per-agent mutation,
    # which would otherwise crash on a half-initialized instance and clobber each
    # agent's specialized tools/LLM.
    def set_tools(self, tools: list[BaseTool]) -> None:
        self._tools = tools

    def set_verbose(self, verbose: bool) -> None:
        self._verbose = verbose

    def set_llm(self, llm: Optional[LLM]) -> None:
        self._llm = llm

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
            return cast(LLM, self._llm)

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

        return LLM(**config)

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
                preferred_model="datarobot/anthropic/claude-sonnet-4-5-20250929",
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
                preferred_model="datarobot/anthropic/claude-sonnet-4-5-20250929"
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

    @property
    def crew(self) -> Crew:
        """Build (and cache) the hierarchical Crew.

        Cached so that callers which configure the crew before invoking it (e.g.
        the dragent entrypoint setting ``agent.crew.stream = True``) mutate the
        same instance that ``invoke`` later runs. The knowledge-base tools hold a
        reference to ``self.knowledge_base_files``, which is mutated in place by
        ``make_kickoff_inputs``, so caching does not stale the KB contents.

        ``stream=True`` so ``invoke`` can stream the manager's synthesized answer to
        the user token-by-token (first token arrives long before the full multi-agent
        run finishes — markedly faster *to the user* than batching the whole answer at
        the end). ``akickoff`` then returns a ``CrewStreamingOutput`` we async-iterate.
        """
        if self._crew is None:
            self._crew = Crew(
                agents=self.agents,
                tasks=self.tasks,
                verbose=self.verbose,
                process=Process.hierarchical,
                manager_agent=self.manager_agent,
            )
        return self._crew

    def _set_otel_usage_attributes(self, usage_metrics: UsageMetrics) -> None:
        """Emit GenAI semantic-convention token usage on the active span."""
        span = trace.get_current_span()
        if not span.is_recording():
            return

        usage_attr_map = {
            "prompt_tokens": "gen_ai.usage.input_tokens",
            "completion_tokens": "gen_ai.usage.output_tokens",
        }

        for usage_key, attribute_name in usage_attr_map.items():
            value = usage_metrics.get(usage_key)
            if not isinstance(value, (int, float)):
                continue
            span.set_attribute(attribute_name, int(value))

    # Specialist roles whose progress is surfaced to the UI as task_progress
    # chunks. The Manager Agent is deliberately excluded — its delegation/ReAct
    # text is the crew's internal scaffolding, not user-facing progress, and its
    # *final* synthesized answer is what we stream as the real answer.
    _AGENT_DISPLAY_TASK: dict[str, str] = {
        "Document Agent": "Analyzing content",
        "Knowledge Base Agent": "Analyzing knowledge base",
        "Files Agent": "Analyzing files",
    }
    _MANAGER_ROLE = "Manager Agent"
    _FINAL_ANSWER_MARKER = "Final Answer:"

    def _task_progress_chunk(
        self, task_name: str, agent_name: str, status: str
    ) -> tuple[TextMessageChunkEvent, None, UsageMetrics]:
        """Build a task_progress JSON chunk consumed by the web app's TaskProgressProcessor.

        The UI treats any ``delta.content`` starting with ``{"task_progress`` as a
        workflow-progress event (not answer text), so these never pollute the answer.
        """
        zero: UsageMetrics = {
            "completion_tokens": 0,
            "prompt_tokens": 0,
            "total_tokens": 0,
        }
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

    async def invoke(self, run_agent_input: Any) -> InvokeReturn:
        """Stream the crew's answer to the user in real time (crewai 1.11 streaming).

        The crew runs with ``stream=True``; ``crew.akickoff`` returns a
        ``CrewStreamingOutput`` we async-iterate. As chunks arrive we:

        * Surface specialist-agent transitions (Document / Knowledge Base / Files)
          as ``task_progress`` JSON chunks the web UI renders as workflow steps. The
          Manager Agent is skipped here.
        * Stream the Manager Agent's *final synthesized answer* to the user
          token-by-token. Because the hierarchical manager's TEXT stream also
          contains ReAct scaffolding ("Thought:/Action:/Action Input:") that the web
          UI would otherwise accumulate into the answer, we gate answer output on the
          ``Final Answer:`` marker: only manager text *after* that marker is streamed
          as the answer. This yields true progressive streaming of the real answer
          with zero ReAct/delegation leakage.

        After the stream drains, ``streaming_output.result`` is the final
        ``CrewOutput`` (``.raw`` + ``token_usage``). ``.raw`` is the source of truth
        for the answer; if marker-gated streaming emitted nothing (e.g. a manager
        response without the standard marker), we fall back to emitting ``.raw`` as a
        single chunk so the user always gets the answer.
        """
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

        usage_metrics = default_usage_metrics()
        pipeline_interactions = None

        with crewai_event_bus.scoped_handlers():
            ragas_listener = CrewAIRagasEventListener()
            ragas_listener.setup_listeners(crewai_event_bus)

            kickoff_inputs = self.make_kickoff_inputs(user_prompt_content)
            crew = self.crew
            crew.stream = True

            logger.info("[invoke] Starting crew with stream=True via akickoff")
            streaming_output = await crew.akickoff(inputs=kickoff_inputs)

            answer_message_id = str(uuid.uuid4())
            current_specialist: str | None = None
            answer_streamed = False
            # Buffer manager text until the Final Answer marker is seen, then stream
            # everything after it. The buffer also handles a marker split across
            # chunk boundaries.
            manager_buffer = ""
            past_marker = False

            if not isinstance(streaming_output, CrewStreamingOutput):
                # stream=True should always yield CrewStreamingOutput; guard anyway.
                response_text = str(getattr(streaming_output, "raw", ""))
                usage_metrics = self._extract_usage_metrics(streaming_output)
                self._set_otel_usage_attributes(usage_metrics)
                pipeline_interactions = self.create_pipeline_interactions_from_messages(
                    ragas_listener.messages
                )
                if response_text:
                    yield (
                        TextMessageChunkEvent(
                            type=EventType.TEXT_MESSAGE_CHUNK,
                            message_id=answer_message_id,
                            delta=response_text,
                        ),
                        None,
                        usage_metrics,
                    )
                yield (
                    RunFinishedEvent(
                        type=EventType.RUN_FINISHED,
                        thread_id=thread_id,
                        run_id=run_id,
                    ),
                    pipeline_interactions,
                    usage_metrics,
                )
                return

            async for chunk in streaming_output:
                role = chunk.agent_role or ""

                # Surface specialist transitions as task_progress; skip the manager.
                if role and role != self._MANAGER_ROLE:
                    if role != current_specialist:
                        if current_specialist:
                            yield self._task_progress_chunk(
                                task_name=self._AGENT_DISPLAY_TASK.get(
                                    current_specialist, "Working"
                                ),
                                agent_name=current_specialist,
                                status="task_completed",
                            )
                        yield self._task_progress_chunk(
                            task_name=self._AGENT_DISPLAY_TASK.get(role, "Working"),
                            agent_name=role,
                            status="task_started",
                        )
                        current_specialist = role
                elif role == self._MANAGER_ROLE and current_specialist:
                    # Control returned to the manager: close the open specialist step.
                    yield self._task_progress_chunk(
                        task_name=self._AGENT_DISPLAY_TASK.get(
                            current_specialist, "Working"
                        ),
                        agent_name=current_specialist,
                        status="task_completed",
                    )
                    current_specialist = None

                if chunk.chunk_type != StreamChunkType.TEXT or not chunk.content:
                    continue

                # Only the manager's *final answer* is streamed to the user.
                if role != self._MANAGER_ROLE:
                    continue

                if past_marker:
                    answer_streamed = True
                    yield (
                        TextMessageChunkEvent(
                            type=EventType.TEXT_MESSAGE_CHUNK,
                            message_id=answer_message_id,
                            delta=chunk.content,
                        ),
                        None,
                        zero,
                    )
                    continue

                manager_buffer += chunk.content
                marker_idx = manager_buffer.find(self._FINAL_ANSWER_MARKER)
                if marker_idx == -1:
                    continue
                past_marker = True
                tail = manager_buffer[
                    marker_idx + len(self._FINAL_ANSWER_MARKER) :
                ].lstrip()
                manager_buffer = ""
                if tail:
                    answer_streamed = True
                    yield (
                        TextMessageChunkEvent(
                            type=EventType.TEXT_MESSAGE_CHUNK,
                            message_id=answer_message_id,
                            delta=tail,
                        ),
                        None,
                        zero,
                    )

            if current_specialist:
                yield self._task_progress_chunk(
                    task_name=self._AGENT_DISPLAY_TASK.get(
                        current_specialist, "Working"
                    ),
                    agent_name=current_specialist,
                    status="task_completed",
                )

            crew_output = streaming_output.result
            usage_metrics = self._extract_usage_metrics(crew_output)
            self._set_otel_usage_attributes(usage_metrics)
            pipeline_interactions = self.create_pipeline_interactions_from_messages(
                ragas_listener.messages
            )

            # Fallback: if marker-gated streaming produced no answer text (manager
            # answered without the standard marker), emit the authoritative .raw.
            if not answer_streamed:
                response_text = str(crew_output.raw)
                if response_text:
                    yield (
                        TextMessageChunkEvent(
                            type=EventType.TEXT_MESSAGE_CHUNK,
                            message_id=answer_message_id,
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
    # The agent builds its own LLM via MyAgent.llm() (gateway fallback + identity
    # headers), so we deliberately do not pass `llm=`. MCP tools are injected by
    # the wrapper via agent.set_tools() using this factory, which keeps the MCP
    # context open for the lifetime of the (possibly streaming) invocation.
    mcp_tools_factory = lambda: mcp_tools_context(mcp_config)  # noqa: E731
    agent = MyAgent(
        verbose=completion_create_params.get("verbose", True),  # type: ignore[arg-type]
        timeout=completion_create_params.get("timeout", 300),  # type: ignore[arg-type]
        forwarded_headers=forwarded_headers,  # type: ignore[arg-type]
    )
    return await agent_chat_completion_wrapper(
        agent, completion_create_params, mcp_tools_factory
    )
