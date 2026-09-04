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
import logging
import os
from collections.abc import AsyncGenerator
from typing import Annotated, Any

from ag_ui.core import RunAgentInput
from datarobot_genai.core.telemetry.agent import instrument
from datarobot_genai.crewai.telemetry import instrument as instrument_crewai
from datarobot_genai.dragent.frontends.response import DRAgentEventResponse
from nat.builder.builder import Builder
from nat.builder.framework_enum import LLMFrameworkEnum
from nat.cli.register_workflow import register_per_user_function
from nat.data_models.agent import AgentBaseConfig
from nat.data_models.component_ref import FunctionGroupRef

logger = logging.getLogger(__name__)

DEFAULT_GUNICORN_WORKER_TIMEOUT_SECONDS = 600


def _raise_gunicorn_worker_timeout() -> None:
    """Raise gunicorn's default 30s worker timeout for the deployed dragent_fastapi front end.

    ``nat dragent serve --use_gunicorn true`` (nvidia-nat's
    ``FastApiFrontEndPluginWorker.run``) builds gunicorn's ``StandaloneApplication``
    with a hardcoded options dict (``bind``/``workers``/``worker_class`` only) and
    overrides ``load_config`` without calling ``super().load_config()``. That means
    ``GUNICORN_CMD_ARGS``, a ``gunicorn.conf.py``, and a ``--timeout`` CLI flag are all
    silently ignored — there is no supported way to raise gunicorn's default 30s worker
    timeout for this front end today. A CrewAI hierarchical crew makes several
    sequential LLM calls per turn and routinely exceeds 30s, so the worker gets
    SIGABRT'd mid-stream and the client is left with a truncated/empty response.

    Patching the ``Setting`` subclasses' class-level ``default`` before gunicorn's
    ``Config()`` is instantiated changes what every subsequently created ``Timeout``/
    ``GracefulTimeout`` setting defaults to, without needing a supported hook. This
    module is a ``nat.plugins`` entry point, imported early enough in process startup —
    well before ``dragent serve`` reaches gunicorn setup — for the patch to take
    effect. Remove this once nvidia-nat exposes a real way to configure it.
    """
    try:
        import gunicorn.config as gunicorn_config
    except ImportError:
        # gunicorn isn't installed/used in this serving mode (e.g. local dev via
        # dev.py, or the DRUM fallback path) — nothing to patch.
        return

    # DataRobot's "numeric" runtime parameters surface as floats (e.g. "600.0"),
    # so parse via float() before truncating to an int. Any exception here would
    # abort loading the `crewai_agent` plugin entirely, taking down the whole agent,
    # so a malformed override must never be allowed to raise.
    raw_value = os.environ.get("AGENT_GUNICORN_WORKER_TIMEOUT")
    try:
        timeout_seconds = (
            int(float(raw_value))
            if raw_value
            else DEFAULT_GUNICORN_WORKER_TIMEOUT_SECONDS
        )
    except (TypeError, ValueError):
        logger.warning(
            "Invalid AGENT_GUNICORN_WORKER_TIMEOUT=%r, falling back to %ss",
            raw_value,
            DEFAULT_GUNICORN_WORKER_TIMEOUT_SECONDS,
        )
        timeout_seconds = DEFAULT_GUNICORN_WORKER_TIMEOUT_SECONDS

    gunicorn_config.Timeout.default = timeout_seconds
    gunicorn_config.GracefulTimeout.default = timeout_seconds
    logger.info(
        "Raised gunicorn worker/graceful timeout defaults to %ss", timeout_seconds
    )


_raise_gunicorn_worker_timeout()

# INSTRUMENTATION CALL IS REQUIRED TO SETUP TRACING AND TELEMETRY FOR AGENTS
instrument()
instrument_crewai()


class CrewaiAgentConfig(AgentBaseConfig, name="crewai_agent"):  # type: ignore[call-arg, misc]
    """NAT config for the CrewAI agent.

    Extends AgentBaseConfig which provides: llm_name, description, verbose.
    The LLM is managed by NAT and accessed via builder.get_llm().
    """

    tool_names: list[FunctionGroupRef] = []


@register_per_user_function(  # type: ignore[untyped-decorator]
    config_type=CrewaiAgentConfig,
    input_type=RunAgentInput,
    streaming_output_type=DRAgentEventResponse,
    framework_wrappers=[LLMFrameworkEnum.CREWAI],
)
async def crewai_agent(
    config: CrewaiAgentConfig, builder: Builder
) -> AsyncGenerator[Any, None]:
    from datarobot_genai.core.mcp import MCPConfig
    from datarobot_genai.crewai.mcp import mcp_tools_context
    from datarobot_genai.dragent.context import (
        extract_authorization_from_context,
        extract_datarobot_headers_from_context,
    )
    from datarobot_genai.dragent.frontends.converters import (
        aggregate_dragent_event_responses,
    )
    from nat.builder.function_info import FunctionInfo, Streaming

    from agent.myagent import MyAgent

    llm = await builder.get_llm(config.llm_name, wrapper_type=LLMFrameworkEnum.CREWAI)

    additional_params = getattr(llm, "additional_params", None)
    if isinstance(additional_params, dict):
        additional_params.pop("stream_options", None)

    # Fetch workflow tools (from tool_names in workflow config) as CrewAI-compatible tools
    workflow_tools = await builder.get_tools(
        config.tool_names, wrapper_type=LLMFrameworkEnum.CREWAI
    )

    async def _response_fn(
        input_message: RunAgentInput,
    ) -> Annotated[
        AsyncGenerator[DRAgentEventResponse, None],
        # Streaming tells NAT how to go from a list of streaming events to a single response
        # object for non-streaming routes.
        Streaming(convert=aggregate_dragent_event_responses),
    ]:
        # Agent should have access to request-specific headers and authorization context
        forwarded_headers = extract_datarobot_headers_from_context()
        authorization_context = extract_authorization_from_context()
        mcp_config = MCPConfig(
            forwarded_headers=forwarded_headers,
            authorization_context=authorization_context,
        )
        async with mcp_tools_context(mcp_config) as mcp_tools:
            tools = workflow_tools + mcp_tools
            agent = MyAgent(
                llm=llm,
                verbose=config.verbose,
                forwarded_headers=forwarded_headers,
                tools=tools,
            )

            async for event, pipeline_interactions, usage_metrics in agent.invoke(
                input_message
            ):
                yield DRAgentEventResponse(
                    events=[event],
                    usage_metrics=usage_metrics,
                    pipeline_interactions=pipeline_interactions,
                )

    yield FunctionInfo.from_fn(
        _response_fn,
        description=config.description,
    )
