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
Core and first Pulumi set of resources.
"""

import os
from pathlib import Path

from datarobot_pulumi_utils.pulumi.stack import PROJECT_NAME
import pulumi
import pulumi_datarobot as datarobot


__all__ = ["use_case", "project_dir"]

project_dir = Path(__file__).parent.parent

if use_case_id := os.environ.get("DATAROBOT_DEFAULT_USE_CASE"):
    pulumi.info(f"Using existing use case '{use_case_id}'")

    use_case = datarobot.UseCase.get(
        id=use_case_id,
        resource_name="Talk to My Docs [PRE-EXISTING]",
    )
else:
    use_case = datarobot.UseCase(
        resource_name=f"Talk to My Docs [{PROJECT_NAME}]",
        description="""*Talk to My Docs** delivers a seamless **talk-to-your-docs** experience, transforming documents search and summary. Simply connect the application with your document sources. Then, ask a question, and the agents will work with you to achieve your goals.""",
    )
