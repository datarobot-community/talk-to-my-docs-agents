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
"""
This LLM configuration option is useful when you already have an LLM Deployed.
It will pull it into the playground and use case. It isn't sufficient if you
have a registered model you would like added to an LLM Blueprint and deployed.
For that, you'll need to choose the "registered_model_llm.py" option
"""

import os
from datarobot_pulumi_utils.pulumi import export
from datarobot_pulumi_utils.pulumi.stack import PROJECT_NAME
import pulumi
import pulumi_datarobot as datarobot

from . import use_case
from .libllm import (
    validate_feature_flags,
    verify_llm,
)

__all__ = [
    "custom_model_runtime_parameters",
    "app_runtime_parameters",
    "default_model",
    "llm_application_name",
    "llm_resource_name",
]

REQUIRED_FEATURE_FLAGS = {
    "ENABLE_MLOPS": True,
    "ENABLE_CUSTOM_INFERENCE_MODEL": True,
    "ENABLE_PUBLIC_NETWORK_ACCESS_FOR_ALL_CUSTOM_MODELS": True,
    "ENABLE_MLOPS_TEXT_GENERATION_TARGET_TYPE": True,
}

LLM_DEPLOYMENT_ID = os.environ["LLM_DEPLOYMENT_ID"]

llm_application_name: str = "llm"
llm_resource_name: str = "[llm]"
default_model: str = os.environ.get(
    "LLM_DEFAULT_MODEL", "datarobot/datarobot-deployed-llm"
)

if not default_model.startswith("datarobot/"):
    default_model = f"datarobot/{default_model}"

# Verify everything is working
validate_feature_flags(REQUIRED_FEATURE_FLAGS)
verify_llm(model_id=f"{default_model}", deployment_id=LLM_DEPLOYMENT_ID)

playground = datarobot.Playground(
    use_case_id=use_case.id,
    resource_name=f"Talk to My Docs Playground [{PROJECT_NAME}]",
)
proxy_llm_deployment = datarobot.Deployment.get(
    resource_name=f"Talk to My Docs Existing LLM Deployment [{PROJECT_NAME}]",
    id=LLM_DEPLOYMENT_ID,
)
prediction_environment = datarobot.PredictionEnvironment.get(
    resource_name="Existing LLM Prediction Environment",
    id=proxy_llm_deployment.prediction_environment_id,
)
app_runtime_parameters = [
    datarobot.ApplicationSourceRuntimeParameterValueArgs(
        key=llm_application_name.upper() + "_DEPLOYMENT_ID",
        type="string",
        value=proxy_llm_deployment.id,
    ),
    datarobot.ApplicationSourceRuntimeParameterValueArgs(
        key=llm_application_name.upper() + "_DEFAULT_MODEL",
        type="string",
        value=default_model,
    ),
    datarobot.ApplicationSourceRuntimeParameterValueArgs(
        key=llm_application_name.upper() + "_DEFAULT_MODEL_FRIENDLY_NAME",
        type="string",
        value=proxy_llm_deployment.label,
    ),
    datarobot.ApplicationSourceRuntimeParameterValueArgs(
        key="USE_DATAROBOT_LLM_GATEWAY",
        type="string",
        value="0",
    ),
]
custom_model_runtime_parameters = [
    datarobot.CustomModelRuntimeParameterValueArgs(
        key="LLM_DEPLOYMENT_ID",
        type="string",
        value=proxy_llm_deployment.id,
    ),
    datarobot.CustomModelRuntimeParameterValueArgs(
        key=llm_application_name.upper() + "_DEFAULT_MODEL",
        type="string",
        value=default_model,
    ),
    datarobot.CustomModelRuntimeParameterValueArgs(
        key="USE_DATAROBOT_LLM_GATEWAY",
        type="string",
        value="0",
    ),
]

pulumi.export(
    "Deployment ID " + proxy_llm_deployment.pulumi_resource_name,
    proxy_llm_deployment.id,
)
export("LLM_DEPLOYMENT_ID", proxy_llm_deployment.id)
export("LLM_DEFAULT_MODEL", default_model)
export("LLM_DEFAULT_MODEL_FRIENDLY_NAME", proxy_llm_deployment.label)
export("USE_DATAROBOT_LLM_GATEWAY", "0")
