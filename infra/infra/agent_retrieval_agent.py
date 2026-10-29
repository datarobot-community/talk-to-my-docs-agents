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

"""Entry router: picks the agent's deployment runtime and re-exports its outputs.

The only place ``ENABLE_AGENT_ON_WORKLOAD_API`` is checked. ``deployment.py``
(Custom Models, today's default) and ``workload.py`` (Workload API) are both
self-contained and never check this flag or import each other -- see
``agent_retrieval_agent_infra/base.py`` for the config shared by both.
"""

import os
from typing import Any

import pulumi

from .agent_retrieval_agent_infra import base
from .agent_retrieval_agent_infra.deployment import provision_deployment_agent
from .agent_retrieval_agent_infra.workload import provision_workload_agent


def _is_truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("true", "1", "yes", "enabled")


ENABLE_AGENT_ON_WORKLOAD_API = _is_truthy_env("ENABLE_AGENT_ON_WORKLOAD_API")

pulumi.export(
    "Agent Runtime " + base.agent_retrieval_agent_asset_name,
    "workload-api" if ENABLE_AGENT_ON_WORKLOAD_API else "custom-model",
)

_shared_agent_runtime_parameters = base.build_shared_agent_runtime_parameters()

_agent_exports: dict[str, Any]
if ENABLE_AGENT_ON_WORKLOAD_API:
    _agent_exports = provision_workload_agent(_shared_agent_runtime_parameters)
else:
    _agent_exports = provision_deployment_agent(_shared_agent_runtime_parameters)

# Re-exported for backward compatibility with the (still default) Custom
# Models path -- consumers outside this component read these attribute names
# off `infra.agent_retrieval_agent`. None of them exist when the other runtime is active
# (e.g. `agent_retrieval_agent_execution_environment` is None in the image-URI Workload
# scenario, since there is no execution environment to report).
agent_retrieval_agent_application_name = base.agent_retrieval_agent_application_name
agent_retrieval_agent_application_path = base.agent_retrieval_agent_application_path

agent_retrieval_agent_execution_environment = _agent_exports["execution_environment"]
agent_retrieval_agent_agent_deployment = _agent_exports["deployment"]
agent_retrieval_agent_workload = _agent_exports["workload"]
agent_retrieval_agent_custom_model = _agent_exports.get("custom_model")
agent_retrieval_agent_agent_deployment_id = _agent_exports.get("agent_deployment_id")
agent_retrieval_agent_prediction_environment = _agent_exports.get(
    "prediction_environment"
)
agent_retrieval_agent_registered_model_args = _agent_exports.get(
    "registered_model_args"
)
agent_retrieval_agent_deployment_args = _agent_exports.get("deployment_args")
agent_retrieval_agent_agent_serving_endpoint = _agent_exports["agent_serving_endpoint"]
agent_retrieval_agent_agent_a2a_endpoint = _agent_exports["agent_a2a_endpoint"]

agent_retrieval_agent_app_runtime_parameters = _agent_exports["app_runtime_parameters"]
agent_retrieval_agent_agent_runtime_parameters = _agent_exports[
    "agent_runtime_parameters"
]

__all__ = [
    "agent_retrieval_agent_agent_deployment",
    "agent_retrieval_agent_agent_deployment_id",
    "agent_retrieval_agent_agent_runtime_parameters",
    "agent_retrieval_agent_app_runtime_parameters",
    "agent_retrieval_agent_application_name",
    "agent_retrieval_agent_application_path",
    "agent_retrieval_agent_execution_environment",
    "agent_retrieval_agent_prediction_environment",
    "agent_retrieval_agent_custom_model",
    "agent_retrieval_agent_deployment_args",
    "agent_retrieval_agent_agent_deployment",
    "agent_retrieval_agent_workload",
    "agent_retrieval_agent_agent_serving_endpoint",
    "agent_retrieval_agent_agent_a2a_endpoint",
    "agent_retrieval_agent_app_runtime_parameters",
    "agent_retrieval_agent_agent_runtime_parameters",
]
