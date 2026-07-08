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
from nat.data_models.agent import AgentBaseConfig

from agent.register import CrewaiAgentConfig, crewai_agent


class TestRegisterModule:
    """Tests that the NAT register module loads correctly and has the expected structure."""

    def test_config_class_is_agent_base_config(self):
        """Verify the config class is a subclass of AgentBaseConfig."""
        assert issubclass(CrewaiAgentConfig, AgentBaseConfig)

    def test_registered_function_is_callable(self):
        """Verify the registered function exists and is callable."""
        assert callable(crewai_agent)
