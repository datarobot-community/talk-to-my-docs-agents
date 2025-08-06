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
# hi
import os
import re
from typing import Any, Dict, Optional, Union

from config import Config
from core.document_loader import SUPPORTED_FILE_TYPES
from crewai import LLM, Agent, Crew, CrewOutput, Task
from helpers import CrewAIEventListener, create_inputs_from_completion_params
from openai.types.chat import CompletionCreateParams
from ragas.messages import AIMessage
from tool import DocumentReadTool, FileListTool, KnowledgeBaseContentTool

DEFAULT_MODEL = "datarobot/azure/gpt-4o-mini"


class MyAgent:
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
            **kwargs: Any: Additional keyword arguments passed to the agent.
                Contains any parameters received in the CompletionCreateParams.

        Returns:
            None
        """
        self.api_key = api_key or os.environ.get("DATAROBOT_API_TOKEN")
        self.api_base = api_base or os.environ.get("DATAROBOT_ENDPOINT")
        self.model = model
        self.config = Config()
        if isinstance(verbose, str):
            self.verbose = verbose.lower() == "true"
        elif isinstance(verbose, bool):
            self.verbose = verbose
        self.event_listener = CrewAIEventListener()
        self.knowledge_base_files: Dict[str, dict[str, str]] = {}

    @property
    def api_base_litellm(self) -> str:
        """Returns a modified version of the API base URL suitable for LiteLLM.

        Strips 'api/v2/' or 'api/v2' from the end of the URL if present.

        Returns:
            str: The modified API base URL.
        """
        if self.api_base:
            return re.sub(r"api/v2/?$", "", self.api_base)
        return "https://api.datarobot.com"

    def model_factory(
        self, model: str = DEFAULT_MODEL, use_deployment: bool = True
    ) -> LLM:
        """Returns the model to use for the LLM.

        If a model is provided, it will be used. Otherwise, the default model will be used.
        If use_deployment is True, the model will be used with the deployment ID
        from the config/environment variable LLM_DEPLOYMENT_ID. If False, it will use the
        LLM Gateway.

        Args:
            model: Optional[str]: The model to use. Defaults to None.

        Returns:
            str: The model to use.
        """
        api_base = (
            f"{self.api_base_litellm}/api/v2/deployments/{self.config.llm_deployment_id}/chat/completions"
            if use_deployment
            else self.api_base_litellm
        )
        return LLM(
            model=model,
            api_base=api_base,
            api_key=self.api_key,
        )

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
    def agent_file_searcher(self) -> Agent:
        return Agent(
            role="File Searcher",
            goal='Find the most closely related filename from a list of file on the topic: "{topic}" as it relates to the question: "{question}". Your services aren\'t needed if the document is in the question already.',
            backstory="You are an expert at searching for files. You can identify the most relevant"
            "file from a list of files. You are given a list of files and a topic. ",
            allow_delegation=False,
            verbose=self.verbose,
            llm=self.model_factory(
                model="datarobot/bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0",
                use_deployment=True,
            ),
        )

    @property
    def task_file_search(self) -> Task:
        return Task(
            description=(
                'Find the most relevant file to "{topic}" and "{question}" from a list of files. You should '
                "always use your tools to determine what files are available. Your task is complete if no files are relevant. "
                f"Please return only a filename that has extensions in the approved extension list. "
                f"This extension list is: {SUPPORTED_FILE_TYPES}. "
                "If no relevant files are found, clearly state 'No relevant files found.'"
            ),
            expected_output="Either a filename with an approved extension, or 'No relevant files found.'",
            agent=self.agent_file_searcher,
            tools=[self.file_list_tool],
            context=[],
        )

    @property
    def agent_writer(self) -> Agent:
        return Agent(
            role="Content Writer",
            goal='Given a filepath and an extremely important question, "{question}", read the contents of the file and '
            "create a summarized answer to the question. ",
            backstory="You are an expert at reading files and answering questions. "
            "You are given a file path and a question. "
            "You should read the file and answer the question. "
            "You should use your tools to read the file. "
            "You will be given the file path that should be used to answer the question.",
            allow_delegation=False,
            verbose=self.verbose,
            llm=self.model_factory(
                model="datarobot/vertex_ai/gemini-2.0-flash-001",
                use_deployment=True,
            ),
        )

    @property
    def task_write(self) -> Task:
        return Task(
            description=(
                "1. Read the contents of the file you are given.\n"
                "2. Think and understand deeply the contents of the file.\n"
                "3. Determine the best way to summarize this information in a concise and understandable way.\n"
                '4. Create a summary that answers the question, "{question}".\n'
                "It is extremely critical that you do your best to answer this question.\n"
                "If no file was provided by the file searcher, state 'No file content available to answer the question.'"
            ),
            expected_output="A well-written summary that answers the question in markdown format, or a clear statement if no file content is available.",
            agent=self.agent_writer,
            tools=[self.document_read_tool],
            context=[self.task_file_search],
        )

    @property
    def document_in_question_agent(self) -> Agent:
        """An agent that can be used to answer questions about a document."""
        return Agent(
            role="Document Question Answerer",
            goal="""
            If the question:\n\"{question}\"\n contains the phrase:
            "Here are the relevant documents with each document separated by three dashes",
            then you should read the pages of the documents from the question and answer the question prior to that phrase.
            """,
            backstory="""
            You are an expert at reading documents and answering questions about them, and when the question includes a document,
            you'll know you should take action to respond to it.
            """,
            allow_delegation=False,
            verbose=self.verbose,
            llm=self.model_factory(
                model="datarobot/vertex_ai/gemini-2.0-flash-001",
                use_deployment=True,
            ),
        )

    @property
    def task_in_question_write(self) -> Task:
        return Task(
            description=(
                '1. Check if the "{question}" contains the phrase "Here is the relevant document with each page separated by three dashes:".\n'
                "2. If it does, separate the question from the document content.\n"
                "3. Think and understand deeply the contents of the document part of the question.\n"
                "4. Determine the best way to summarize this information in a concise and understandable way.\n"
                '5. Create a summary that answers the question part of "{question}".\n'
                '6. If the phrase is not found, respond with "No embedded document found in question."\n'
                "It is extremely critical that you do your best to answer this question.\n"
            ),
            expected_output="A well-written summary in markdown format that answers the question using the embedded document, or a clear statement if no embedded document is found.",
            agent=self.document_in_question_agent,
            context=[],
        )

    @property
    def knowledge_base_file_searcher(self) -> Agent:
        """An agent that searches through knowledge base files to find the most relevant ones."""
        return Agent(
            role="Knowledge Base File Searcher",
            goal="Given a list of files from a knowledge base with limited content previews, identify the most relevant files that would contain information to answer the question: {question}",
            backstory="You are an expert at analyzing file metadata, titles, and content previews to determine which files are most likely to contain relevant information. You work with knowledge base systems where full content isn't immediately available.",
            allow_delegation=False,
            verbose=self.verbose,
            llm=self.model_factory(
                model="datarobot/bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0",
                use_deployment=True,
            ),
        )

    @property
    def task_knowledge_base_file_search(self) -> Task:
        return Task(
            description=(
                "Analyze the knowledge base `files` provided in this JSON:\n\n``` {knowledge_base}\n```\n\n to identify which files are most relevant "
                "for answering the question: \"{question}\". If there is nothing in between the ``` and ``` symbols, respond with 'No knowledge base files available.' "
                'Look at file names, metadata, the topic "{topic}", and any content previews '
                "to make your determination. Select the top 2-3 most relevant files that would likely contain "
                "the information needed to answer the question. You select them by what is assigned the 'uuid' key in the knowledge base json list of files. "
                "DO NOT select any keys such as owner_uuid or project_uuid (these are not file UUIDs). Only the key 'uuid'.\n\n"
                "IMPORTANT: Format your response as a clear list of UUIDs, one per line, like:\n"
                "Selected UUIDs:\n"
                "- 44c6434a-7396-4b05-8ff1-bf1ab7f6000a\n"
                "- 22b19e27-15b8-4238-98f4-d66571aa0c58"
            ),
            expected_output="A clearly formatted list of the most relevant file UUIDs from the knowledge base, with each UUID on its own line, or 'No knowledge base files available.'",
            agent=self.knowledge_base_file_searcher,
            context=[],
        )

    @property
    def knowledge_base_content_answerer(self) -> Agent:
        """An agent that answers questions using the full content of knowledge base files."""
        return Agent(
            role="Knowledge Base Content Answerer",
            goal=(
                'Given a list of file UUIDs and an extremely important question: "{question}", '
                "read the full content of those files to answer the question."
            ),
            backstory=(
                "You are an expert at reading and synthesizing information from multiple documents to provide accurate, well-sourced answers. "
                "You have access to the complete content of knowledge base files and can extract the most relevant information. "
                "You always use the exact UUIDs provided by the previous agent - never make up or guess UUIDs."
            ),
            allow_delegation=False,
            verbose=self.verbose,
            llm=self.model_factory(
                model="datarobot/vertex_ai/gemini-2.0-flash-001",
                use_deployment=True,
            ),
        )

    @property
    def task_knowledge_base_content_answer(self) -> Task:
        return Task(
            description=(
                "IMPORTANT: The Knowledge Base File Searcher has provided you with relevant file UUIDs in its output. "
                "You must carefully examine the context from the previous task to extract these UUIDs. \n"
                "CRITICAL: You MUST use your tool to get the content from those files\n\n"
                "Your task:\n"
                "1. Look at the output from the Knowledge Base File Searcher task in your context\n"
                "2. Find any lines that start with '- ' followed by a UUID (format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)\n"
                "3. Extract ALL UUIDs from those lines - they will look like: 6d9b8079-732e-4b02-99cd-697fe9df9a67\n"
                "4. Use the knowledge base content tool with the extracted UUIDs as a list\n"
                "5. Read and understand the content deeply\n"
                '6. Create a comprehensive answer to the question: "{question}"\n\n'
                "Example: If you see in the context:\n"
                "'Selected UUIDs:\\n- 6d9b8079-732e-4b02-99cd-697fe9df9a67\\n- 22b19e27-15b8-4238-98f4-d66571aa0c58'\n"
                "Then you should call your tool with: ['6d9b8079-732e-4b02-99cd-697fe9df9a67', '22b19e27-15b8-4238-98f4-d66571aa0c58']\n\n"
                "CRITICAL: Never call the tool with an empty list. Always extract the UUIDs from the context first."
            ),
            expected_output="A comprehensive, well-formatted markdown summary answering the question using the knowledge base content.",
            agent=self.knowledge_base_content_answerer,
            tools=[self.knowledge_base_content_tool],
            context=[],
        )

    @property
    def finalizer_agent(self) -> Agent:
        """An agent that coordinates and finalizes the outputs from all other agents."""
        return Agent(
            role="Response Finalizer",
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
            allow_delegation=False,
            verbose=self.verbose,
            llm=self.model_factory(
                model="datarobot/vertex_ai/gemini-2.0-flash-001",
                use_deployment=True,
            ),
        )

    @property
    def task_finalize_response(self) -> Task:
        return Task(
            description=(
                'Analyze all the outputs from the previous agents and create a single, coherent answer to: "{question}". '
                "You have access to:\n"
                "1. File search results and file-based content analysis\n"
                "2. Embedded document analysis (if present in the question)\n"
                "3. Knowledge base search and content analysis\n\n"
                "Your job is to:\n"
                "1. Determine which agents found relevant information\n"
                "2. Synthesize the most relevant and accurate information\n"
                "3. Create a well-formatted, comprehensive response\n"
                "4. Ignore any 'not available' or 'not found' responses\n"
                "5. If multiple sources provide information, combine them intelligently\n"
                "6. If no sources provide useful information, clearly state that no relevant information was found\n\n"
                "Never output raw tool results, file paths, or technical details - only the final answer."
            ),
            expected_output="A single, well-formatted markdown response that directly answers the user's question using the most relevant information found by all agents.",
            agent=self.finalizer_agent,
        )

    def crew(self) -> Crew:
        return Crew(
            agents=[
                self.agent_file_searcher,
                self.agent_writer,
                self.document_in_question_agent,
                self.knowledge_base_file_searcher,
                self.knowledge_base_content_answerer,
                self.finalizer_agent,
            ],
            tasks=[
                self.task_file_search,
                self.task_write,
                self.task_in_question_write,
                self.task_knowledge_base_file_search,
                self.task_knowledge_base_content_answer,
                self.task_finalize_response,
            ],
            verbose=self.verbose,
        )

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

    def run(
        self, completion_create_params: CompletionCreateParams
    ) -> tuple[list[Any], CrewOutput]:
        """Run the agent with the provided completion parameters.

        [THIS METHOD IS REQUIRED FOR THE AGENT TO WORK WITH DRUM SERVER]

        Inputs can be extracted from the completion_create_params in several ways. A helper function
        `create_inputs_from_completion_params` is provided to extract the inputs as json or a string
        from the 'user' portion of the input prompt. Alternatively you can extract and use one or
        more inputs or messages from the completion_create_params["messages"] field.

        Args:
            completion_create_params (CompletionCreateParams): The parameters for
                the completion request, which includes the input topic and other settings.
        Returns:
            tuple[list[Any], CrewOutput]: A tuple containing a list of messages (events) and the crew output.

        """
        # Example helper for extracting inputs as a json from the completion_create_params["messages"]
        # field with the 'user' role: (e.g. {"topic": "Artificial Intelligence"})
        inputs = create_inputs_from_completion_params(completion_create_params)
        # If inputs are a string, convert to a dictionary with 'topic' key for this example.
        if isinstance(inputs, str):
            inputs = {"topic": inputs}

        # Handle knowledge base content extraction and storage
        if "knowledge_base" in inputs:
            # Extract and store encoded_content, remove from working inputs
            self._extract_and_store_knowledge_base_content(inputs["knowledge_base"])
            self.knowledge_base_content_tool.knowledge_base = self.knowledge_base_files
            inputs["topic"] = inputs["knowledge_base"]["description"]
        else:
            inputs["knowledge_base"] = ""
        # Print commands may need flush=True to ensure they are displayed in real-time.
        print("Running agent with inputs:", inputs, flush=True)

        # Run the crew with the inputs
        crew_output = self.crew().kickoff(inputs=inputs)

        # Extract the response text from the crew output
        response_text = str(crew_output.raw)

        # Create a list of events from the event listener
        events = self.event_listener.messages
        if len(events) > 0:
            last_message = events[-1].content
            if last_message != response_text:
                events.append(AIMessage(content=response_text))
        else:
            events = None
        return events, crew_output
