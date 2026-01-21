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
import argparse
import json
from pathlib import Path
from typing import Any, Dict

from agent import MyAgent


def train(
    iterations: int = 5,
    inputs: Dict[str, Any] = {"topic": "CrewAI Training"},
    skip_files: bool = False,
    filename: Path = Path(__file__).parent / "custom_model" / "trained_agents_data.pkl",
) -> None:
    agents = MyAgent()
    if "knowledge_base" in inputs:
        # Extract and store encoded_content, remove from working inputs
        agents._extract_and_store_knowledge_base_content(inputs["knowledge_base"])
        agents.knowledge_base_content_tool.knowledge_base = agents.knowledge_base_files
        inputs["topic"] = inputs["knowledge_base"]["description"]
    else:
        inputs["knowledge_base"] = ""
    crew = agents.crew()
    if skip_files:
        crew.agents = [
            agent for agent in crew.agents if agent.role not in ["File Searcher"]
        ]
        crew.tasks = [
            task for task in crew.tasks if task.name not in ["File List", "File Read"]
        ]
    try:
        crew.train(n_iterations=iterations, inputs=inputs, filename=str(filename))

    except Exception as e:
        raise Exception(f"An error occurred while training the crew: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train the CrewAI agent with customizable parameters"
    )

    parser.add_argument(
        "--iterations",
        type=int,
        default=5,
        help="Number of training iterations (default: 5)",
    )

    parser.add_argument(
        "--inputs",
        type=str,
        help="Path to JSON file containing training inputs (default: agent_inputs.json)",
    )

    parser.add_argument(
        "--filename",
        type=str,
        default="training_data.pkl",
        help="Filename for saving training data (default: training_data.pkl)",
    )

    parser.add_argument(
        "--skip-files",
        action="store_true",
        help="Skip file-related agents and tasks during training",
    )

    args = parser.parse_args()

    # Load inputs from file
    if args.inputs:
        inputs_path = Path(args.inputs)
    else:
        inputs_path = Path(__file__).parent.parent / "agent_inputs.json"

    try:
        with open(inputs_path, "r") as f:
            inputs = json.load(f)
    except FileNotFoundError:
        print(f"Error: Input file '{inputs_path}' not found.")
        print("Using default inputs: {'topic': 'CrewAI Training'}")
        inputs = {"topic": "CrewAI Training"}
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in '{inputs_path}'.")
        print("Using default inputs: {'topic': 'CrewAI Training'}")
        inputs = {"topic": "CrewAI Training"}

    print(f"Training with {args.iterations} iterations")
    print(f"Using inputs: {inputs}")
    print(f"Saving to: {args.filename}")
    print(f"Skip files: {args.skip_files}")

    train(
        iterations=args.iterations,
        inputs=inputs,
        skip_files=args.skip_files,
        filename=args.filename,
    )


if __name__ == "__main__":
    main()
