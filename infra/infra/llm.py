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

import datarobot as dr
import pulumi
import pulumi_datarobot as datarobot
from datarobot_pulumi_utils.pulumi.stack import PROJECT_NAME
from datarobot_pulumi_utils.pulumi.custom_model_deployment import (
    CustomModelDeployment,
    DeploymentArgs,
    RegisteredModelArgs,
)
from datarobot_pulumi_utils.schema.custom_models import CustomModelArgs
from datarobot_pulumi_utils.schema.llms import (
    LLMSettings,
    LLMs,
    LLMBlueprintArgs,
)
from datarobot_pulumi_utils.schema.exec_envs import RuntimeEnvironments

from . import use_case

LLM = LLMs.AZURE_OPENAI_GPT_4_O_MINI

playground = datarobot.Playground(
    use_case_id=use_case.id,
    resource_name=f"Talk to My Docs Playground [{PROJECT_NAME}]",
)

llm_blueprint_args = LLMBlueprintArgs(
    resource_name=f"Talk to My Docs LLM Blueprint [{PROJECT_NAME}]",
    llm_id=LLM.name,
    llm_settings=LLMSettings(
        max_completion_length=4000,
        temperature=0.7,
        top_p=None,
    ),
)

llm_blueprint = datarobot.LlmBlueprint(
    playground_id=playground.id,
    **llm_blueprint_args.model_dump(),
)

custom_model_args = CustomModelArgs(
    resource_name=f"Talk to My Docs Playground Model [{PROJECT_NAME}]",
    name=f"Talk to My Docs Custom Model [{PROJECT_NAME}]",
    target_name="resultText",
    target_type=dr.enums.TARGET_TYPE.TEXT_GENERATION,
    replicas=1,
    base_environment_id=RuntimeEnvironments.PYTHON_312_MODERATIONS.value.id,
)

llm_custom_model = datarobot.CustomModel(
    **custom_model_args.model_dump(exclude_none=True),
    use_case_ids=[use_case.id],
    source_llm_blueprint_id=llm_blueprint.id,
)

registered_model_args = RegisteredModelArgs(
    resource_name=f"Talk to My Docs Registered Model [{PROJECT_NAME}]",
)

prediction_environment = datarobot.PredictionEnvironment(
    resource_name=f"Talk to My Docs Prediction Environment [{PROJECT_NAME}]",
    platform=dr.enums.PredictionEnvironmentPlatform.DATAROBOT_SERVERLESS,
)

deployment_args = DeploymentArgs(
    resource_name=f"Talk to My Docs Deployment [{PROJECT_NAME}]",
    label=f"Talk to My Docs Deployment [{PROJECT_NAME}]",
    association_id_settings=datarobot.DeploymentAssociationIdSettingsArgs(
        column_names=["association_id"],
        auto_generate_id=False,
        required_in_prediction_requests=True,
    ),
    predictions_data_collection_settings=datarobot.DeploymentPredictionsDataCollectionSettingsArgs(
        enabled=True,
    ),
    predictions_settings=(
        datarobot.DeploymentPredictionsSettingsArgs(min_computes=0, max_computes=2)
    ),
)

llm_deployment = CustomModelDeployment(
    resource_name=f"Talk to My Docs LLM deployment [{PROJECT_NAME}]",
    use_case_ids=[use_case.id],
    custom_model_version_id=llm_custom_model.version_id,
    registered_model_args=registered_model_args,
    prediction_environment=prediction_environment,
    deployment_args=deployment_args,
)

app_runtime_parameters = [
    datarobot.ApplicationSourceRuntimeParameterValueArgs(
        key="LLM_DEPLOYMENT_ID",
        type="deployment",
        value=llm_deployment.id,
    ),
]

custom_model_runtime_parameters = [
    datarobot.CustomModelRuntimeParameterValueArgs(
        key="LLM_DEPLOYMENT_ID",
        type="string",
        value=llm_deployment.id,
    )
]

pulumi.export("Deployment ID " + llm_deployment.pulumi_resource_name, llm_deployment.id)
pulumi.export("LLM_DEPLOYMENT_ID", llm_deployment.id)
