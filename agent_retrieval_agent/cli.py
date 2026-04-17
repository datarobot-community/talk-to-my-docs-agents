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
import os
from typing import Any

import click
from datarobot_genai.core.cli import AgentEnvironment
from openai import Stream
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionChunk,
)

from agent import Config

pass_environment = click.make_pass_decorator(AgentEnvironment)


def display_response(response: ChatCompletion, show_output: bool) -> None:
    """Display the response in a formatted way."""
    response_dict = response.model_dump()
    if not show_output:
        with open("execute_output.json", "w") as f:
            json.dump(response_dict, f, indent=2)

    if "pipeline_interactions" in response_dict:
        response_dict["pipeline_interactions"] = "[Truncated for display]"

    if show_output:
        click.echo("\nExecution result:")
        click.echo(json.dumps(response_dict, indent=2))
    else:
        if "choices" in response_dict:
            response_dict["choices"] = "[Truncated for display]"

        # Show only first 200 characters of response
        click.echo("\nExecution result preview:")
        click.echo(json.dumps(response_dict, indent=2))
        click.echo("")
        click.echo("IMPORTANT")
        click.echo(
            "This is a preview of the json result, or only the final message if streaming is enabled."
        )
        click.echo(
            f"To view the full result (including all streaming responses) run "
            f"`cat {os.path.abspath('execute_output.json')}`."
        )
        click.echo(
            "To display the full result inline, rerun with the `--show_output` flag."
        )


def display_response_streaming(response: Stream[ChatCompletionChunk]) -> None:
    click.echo("\nStreaming response:")
    for chunk in response:
        chunk_dict = chunk.model_dump()
        if "pipeline_interactions" in chunk_dict:
            chunk_dict["pipeline_interactions"] = "[Truncated for display]"
        click.echo(json.dumps(chunk_dict, indent=2))


def is_dragent_mode() -> bool:
    """Check if dragent server mode is enabled via ENABLE_DRAGENT_SERVER env var."""
    return os.environ.get("ENABLE_DRAGENT_SERVER", "false").lower() == "true"


def build_dragent_payload(user_prompt: str) -> dict[str, Any]:
    """Build an AG-UI RunAgentInput payload for the dragent /generate/stream endpoint."""
    from uuid import uuid4  # noqa: PLC0415

    return {
        "threadId": str(uuid4()),
        "runId": str(uuid4()),
        "state": [],
        "tools": [],
        "context": [],
        "forwardedProps": {},
        "messages": [
            {
                "id": str(uuid4()),
                "role": "user",
                "content": user_prompt,
            }
        ],
    }


def execute_dragent_stream(
    user_prompt: str,
    url: str,
    headers: dict[str, str] | None = None,
) -> None:
    """POST to a dragent /generate/stream endpoint and print SSE text events."""
    import logging  # noqa: PLC0415

    import httpx  # noqa: PLC0415

    logger = logging.getLogger(__name__)
    payload = build_dragent_payload(user_prompt)
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)

    try:
        with httpx.stream(
            "POST", url, json=payload, headers=request_headers, timeout=300
        ) as resp:
            resp.raise_for_status()
            click.echo("\nStreaming response:")
            for line in resp.iter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                except json.JSONDecodeError:
                    logger.debug("Skipping malformed SSE data: %s", line)
                    continue

                # DRAgentEventResponse wraps events in an "events" list
                events = data.get("events", [data])
                for ev in events:
                    event_type = ev.get("type", "")
                    if event_type in ("TEXT_MESSAGE_CONTENT", "TEXT_MESSAGE_CHUNK"):
                        click.echo(ev.get("delta", ""), nl=False)
                    elif event_type == "TEXT_MESSAGE_END":
                        click.echo("")
                    elif event_type == "RUN_FINISHED":
                        click.echo("\nRun finished.")
                    else:
                        logger.debug("Unhandled SSE event type: %s", event_type)
    except httpx.ConnectError:
        raise click.ClickException(
            f"Could not connect to {url}. Is the dragent server running?"
        )
    except httpx.HTTPStatusError as e:
        raise click.ClickException(f"HTTP error from dragent server: {e}")


@click.group()
@click.option("--api_token", default=None, help="API token for authentication.")
@click.option("--base_url", default=None, help="Base URL for the API.")
@click.pass_context
def cli(
    ctx: Any,
    api_token: str | None,
    base_url: str | None,
) -> None:
    """A CLI for interacting executing agent custom models using the chat endpoint and OpenAI completions.

    For more information on the main CLI commands and all available options, run the help command:
    > task cli -- execute --help
    > task cli -- execute-deployment --help

    Common examples:

    # Run the agent with a string user prompt
    > task cli -- execute --user_prompt "Artificial Intelligence"

    # Run the agent with a JSON user prompt    > task cli -- execute --user_prompt '{"topic": "Artificial Intelligence"}'

    # Run the agent with a JSON file containing the full chat completion json; include prior messages for chat history.
    # Prior messages are injected as chat_history when make_kickoff_inputs() declares a "chat_history" key.
    > task cli -- execute --completion_json "example-completion.json"
    > task cli -- execute --completion_json "example-chat-history-completion.json"

    # Run the deployed agent with a string user prompt [Other prompt methods are also supported similar to execute]
    > task cli -- execute-deployment --user_prompt "Artificial Intelligence" --deployment_id 680a77a9a3

    """
    ctx.obj = AgentEnvironment(api_token, base_url)


@cli.command()
@pass_environment
@click.option("--user_prompt", default="", help="Input to use for chat.")
@click.option("--completion_json", default="", help="Path to json to use for chat.")
@click.option("--stream", is_flag=True, help="Enable streaming response.")
@click.option(
    "--show_output", is_flag=True, help="Show the full stored execution result."
)
def execute(
    environment: Any,
    user_prompt: str,
    completion_json: str,
    show_output: bool,
    stream: bool,
) -> None:
    """Execute agent code locally using OpenAI completions.

    Examples:

    # Run the agent with a string user prompt
    > task cli -- execute --user_prompt "Artificial Intelligence"

    # Run the agent with streaming enabled
    > task cli -- execute --user_prompt "Artificial Intelligence" --stream

    # Run the agent with a string user prompt and show full output
    > task cli -- execute --user_prompt "Artificial Intelligence" --show_output

    # Run the agent with a JSON user prompt    > task cli -- execute --user_prompt '{"topic": "Artificial Intelligence"}'

    # Run the agent with a JSON file containing the full chat completion json; include prior messages for chat history.
    # Prior messages are injected as chat_history when make_kickoff_inputs() declares a "chat_history" key.
    > task cli -- execute --completion_json "example-completion.json"
    > task cli -- execute --completion_json "example-chat-history-completion.json"
    """
    if len(user_prompt) == 0 and len(completion_json) == 0:
        raise click.UsageError("User prompt message or completion json must provided.")

    if is_dragent_mode():
        if not user_prompt:
            raise click.UsageError("dragent mode requires --user_prompt.")
        click.echo("Running agent (dragent mode)...")
        config = Config()
        execute_dragent_stream(
            user_prompt,
            url=f"http://localhost:{config.local_dev_port}/generate/stream",
        )
        return

    click.echo("Running agent...")
    response = environment.interface.local(
        user_prompt=user_prompt,
        completion_json=completion_json,
        stream=stream,
        config=Config(),
    )
    if stream:
        display_response_streaming(response)
    else:
        display_response(response, show_output)


@cli.command()
@pass_environment
@click.option("--user_prompt", default="", help="Input to use for predict.")
@click.option("--custom_model_id", default="", help="ID for the deployment.")
def execute_custom_model(
    environment: Any, user_prompt: str, custom_model_id: str
) -> None:
    """Query a custom model using the command line for OpenAI completions. Custom models will execute inside an
    ephemeral CodeSpace environment. This can also be done through the DataRobot Playground UI.

    Example:

    # Run the agent with a string user prompt
    > task cli -- execute-custom-model --user_prompt "Artificial Intelligence" --custom_model_id 680a77a9a3

    # Run the agent with a JSON user prompt
    > task cli -- execute-custom-model --user_prompt '{"topic": "Artificial Intelligence"}' --custom_model_id 680a77a9a3
    """
    if is_dragent_mode():
        raise click.UsageError(
            "execute-custom-model is not supported in dragent mode. "
            "Use execute-deployment instead."
        )
    if len(user_prompt) == 0:
        raise click.UsageError("User prompt message must be provided.")
    if len(custom_model_id) == 0:
        raise click.UsageError("Custom Model ID must be provided.")

    click.echo("Querying deployment...")
    response = environment.interface.custom_model(
        custom_model_id=custom_model_id,
        user_prompt=user_prompt,
    )
    click.echo(response)


@cli.command()
@pass_environment
@click.option("--user_prompt", default="", help="Input to use for predict.")
@click.option("--completion_json", default="", help="Path to json to use for chat.")
@click.option("--deployment_id", default="", help="ID for the deployment.")
@click.option(
    "--show_output", is_flag=True, help="Show the full stored execution result."
)
@click.option("--stream", is_flag=True, help="Enable streaming response.")
def execute_deployment(
    environment: Any,
    user_prompt: str,
    completion_json: str,
    deployment_id: str,
    show_output: bool,
    stream: bool,
) -> None:
    """Query a deployed model using the command line for OpenAI completions.

    Example:

    # Run the agent with a string user prompt
    > task cli -- execute-deployment --user_prompt "Artificial Intelligence" --deployment_id 680a77a9a3

    # Run the agent with a string user prompt and show full output
    > task cli -- execute-deployment --user_prompt "Artificial Intelligence" --show_output --deployment_id 680a77a9a3

    # Run the agent with a string user prompt, streaming enabled
    > task cli -- execute-deployment --user_prompt "Artificial Intelligence" --stream --deployment_id 680a77a9a3

    # Run the agent with a JSON user prompt    > task cli -- execute-deployment --user_prompt '{"topic": "Artificial Intelligence"}' --deployment_id 680a77a9a3

    # Run the agent with a JSON file containing the full chat completion json; include prior messages for chat history.
    # Prior messages are injected as chat_history when make_kickoff_inputs() declares a "chat_history" key.
    > task cli -- execute-deployment --completion_json "example-completion.json" --deployment_id 680a77a9a3
    > task cli -- execute-deployment --completion_json "example-chat-history-completion.json" --deployment_id 680a77a9a3
    """
    if len(user_prompt) == 0 and len(completion_json) == 0:
        raise click.UsageError("User prompt message or completion json must provided.")
    if len(deployment_id) == 0:
        raise click.UsageError("Deployment ID must be provided.")

    if is_dragent_mode():
        if not user_prompt:
            raise click.UsageError("dragent mode requires --user_prompt.")
        if not environment.base_url:
            raise click.UsageError("dragent deployment mode requires --base_url.")
        if not environment.api_token:
            raise click.UsageError("dragent deployment mode requires --api_token.")
        click.echo("Querying deployment (dragent mode)...")
        execute_dragent_stream(
            user_prompt,
            url=f"{environment.base_url}/api/v2/deployments/{deployment_id}/generate/stream",
            headers={"Authorization": f"Bearer {environment.api_token}"},
        )
        return

    click.echo("Querying deployment...")
    response = environment.interface.deployment(
        deployment_id=deployment_id,
        user_prompt=user_prompt,
        completion_json=completion_json,
        stream=stream,
    )
    if stream:
        display_response_streaming(response)
    else:
        display_response(response, show_output)


if __name__ == "__main__":
    cli()
