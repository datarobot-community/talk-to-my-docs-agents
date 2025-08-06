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

import os
import re
import textwrap
from typing import Final, Sequence

import pulumi
import pulumi_datarobot
from datarobot_pulumi_utils.schema.apps import ApplicationSourceArgs
from datarobot_pulumi_utils.schema.apps import CustomAppResourceBundles
from datarobot_pulumi_utils.schema.exec_envs import RuntimeEnvironments
from datarobot_pulumi_utils.pulumi.stack import PROJECT_NAME

from . import use_case, project_dir
from .oauth import app_runtime_parameters as oauth_app_runtime_parameters
from .llm import app_runtime_parameters as llm_app_runtime_parameters
from .agent_retrieval_agent import agent_retrieval_agent_app_runtime_parameters

SESSION_SECRET_KEY: Final[str] = "SESSION_SECRET_KEY"
session_secret_key = os.environ.get(SESSION_SECRET_KEY)
DATABASE_URI: Final[str] = "DATABASE_URI"
database_uri = os.environ.get(
    DATABASE_URI, "sqlite+aiosqlite:////tmp/ttmdocs/.data/talk_to_my_docs.db"
)
STORAGE_PATH: Final[str] = "STORAGE_PATH"
storage_path = os.environ.get(STORAGE_PATH, "/tmp/ttmdocs/.data/storage")

EXCLUDE_PATTERNS = [
    re.compile(pattern)
    for pattern in [
        r".*tests/.*",
        r".*\.coverage",
        r".*\.DS_Store",
        r".*\.pyc",
        r".*\.ruff_cache/.*",
        r".*\.venv/.*",
        r".*\.mypy_cache/.*",
        r".*__pycache__/.*",
        r".*\.pytest_cache/.*",
        r".*htmlcov/.*",
        r".*\.data/.*",
        r".*\.env",
    ]
]


__all__ = [
    "web_app",
    "web_app_env_name",
    "web_app_resource_name",
    "web_app_runtime_parameters",
    "web_app_source",
    "web_application_path",
    "get_web_app_files",
]


def _prep_metadata_yaml(
    runtime_parameter_values: Sequence[
        pulumi_datarobot.ApplicationSourceRuntimeParameterValueArgs
        | pulumi_datarobot.CustomModelRuntimeParameterValueArgs
    ],
) -> None:
    from jinja2 import BaseLoader, Environment

    runtime_parameter_specs = "\n".join(
        [
            textwrap.dedent(
                f"""\
            - fieldName: {param.key}
              type: {param.type}
        """
            )
            for param in runtime_parameter_values
        ]
    )
    if not runtime_parameter_specs:
        runtime_parameter_specs = "    []"
    with open(web_application_path / "metadata.yaml.jinja") as f:
        template = Environment(loader=BaseLoader()).from_string(f.read())
    (web_application_path / "metadata.yaml").write_text(
        template.render(
            additional_params=runtime_parameter_specs,
        )
    )


def get_web_app_files(
    runtime_parameter_values: Sequence[
        pulumi_datarobot.ApplicationSourceRuntimeParameterValueArgs
        | pulumi_datarobot.CustomModelRuntimeParameterValueArgs,
    ],
) -> list[tuple[str, str]]:
    _prep_metadata_yaml(runtime_parameter_values)
    # Get all files from application path, following symlinks
    # When we've upgraded to Python 3.13 we can use Path.glob(reduce_symlinks=True)
    # https://docs.python.org/3.13/library/pathlib.html#pathlib.Path.glob
    source_files = []
    for dirpath, dirnames, filenames in os.walk(web_application_path, followlinks=True):
        for filename in filenames:
            if filename == "metadata.yaml":
                continue
            file_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(file_path, web_application_path)
            source_files.append((os.path.abspath(file_path), rel_path))
    # Add the metadata.yaml file
    source_files.append(
        ((web_application_path / "metadata.yaml").as_posix(), "metadata.yaml")
    )
    source_files = [
        (file_path, file_name)
        for file_path, file_name in source_files
        if not any(
            exclude_pattern.match(file_name) for exclude_pattern in EXCLUDE_PATTERNS
        )
    ]

    return source_files


# Start of Pulumi settings and application infrastructure
web_app_env_name: str = "DATAROBOT_APPLICATION_ID"
web_application_path = project_dir.parent / "web"

web_app_source_args = ApplicationSourceArgs(
    resource_name=f"Talk to My Docs [{PROJECT_NAME}]",
    base_environment_id=RuntimeEnvironments.PYTHON_312_APPLICATION_BASE.value.id,
).model_dump(mode="json", exclude_none=True)

web_app_resource_name: str = f"Talk to My Docs [{PROJECT_NAME}]"

# Set up Runtime Parameters for the Web Application

pulumi.export("SESSION_SECRET_KEY", session_secret_key)
session_secret_cred = pulumi_datarobot.ApiTokenCredential(
    f"Talk to My Docs Session Secret Key [{PROJECT_NAME}]",
    args=pulumi_datarobot.ApiTokenCredentialArgs(
        api_token=str(session_secret_key),
    ),
)
pulumi.export("DATABASE_URI", database_uri)
database_uri_cred = pulumi_datarobot.ApiTokenCredential(
    f"Talk to My Docs Database URI [{PROJECT_NAME}]",
    args=pulumi_datarobot.ApiTokenCredentialArgs(
        api_token=str(database_uri),
    ),
)

general_runtime_params = [
    pulumi_datarobot.ApplicationSourceRuntimeParameterValueArgs(
        type="credential",
        key=SESSION_SECRET_KEY,
        value=session_secret_cred.id,
    ),
    pulumi_datarobot.ApplicationSourceRuntimeParameterValueArgs(
        type="credential",
        key=DATABASE_URI,
        value=database_uri_cred.id,
    ),
    pulumi_datarobot.ApplicationSourceRuntimeParameterValueArgs(
        type="string",
        key=STORAGE_PATH,
        value=storage_path,
    ),
]

web_app_runtime_parameters: list[
    pulumi_datarobot.ApplicationSourceRuntimeParameterValueArgs
] = (
    llm_app_runtime_parameters
    + oauth_app_runtime_parameters
    + agent_retrieval_agent_app_runtime_parameters
    + general_runtime_params
)

web_app_source = pulumi_datarobot.ApplicationSource(
    files=get_web_app_files(runtime_parameter_values=web_app_runtime_parameters),
    runtime_parameter_values=web_app_runtime_parameters,
    resources=pulumi_datarobot.ApplicationSourceResourcesArgs(
        resource_label=CustomAppResourceBundles.CPU_XL.value.id,
    ),
    **web_app_source_args,
)

web_app = pulumi_datarobot.CustomApplication(
    resource_name=web_app_resource_name,
    source_version_id=web_app_source.version_id,
    use_case_ids=[use_case.id],
    allow_auto_stopping=True,
)

pulumi.export(web_app_env_name, web_app.id)
pulumi.export(
    web_app_resource_name,
    web_app.application_url,
)
