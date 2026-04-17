# Agent Development Instructions

## Dependencies Installation

The following command should be run after agent code modification:

```shell
dr task run agent_retrieval_agent:install
```

## Agent Structure

Agent must be implemented in the following location withing the `agent_retrieval_agent/agent` directory. None of the other files outside of this directory are related.



Agent must implement the following components:

### 1. Class Definition

```python
from crewai import LLM, Agent, Task
from datarobot_genai.crewai.agent import CrewAIAgent

class MyAgent(CrewAIAgent):
    """Your agent description here."""
```

**Important**: `MyAgent` class should NOT be renamed!

### 2. Required Properties and Methods in Class Definition

#### `llm()` Method

**CRITICAL**: Do NOT modify, delete, or change this method. It MUST be kept exactly as shown below in the agent implementation:

```python
def llm(
        self,
        auto_model_override: bool = True,
    ) -> LLM:
        api_base = self.litellm_api_base(self.config.llm_deployment_id)
        model = self.model or self.default_model
        if auto_model_override and not self.config.use_datarobot_llm_gateway:
            model = self.default_model
        if self.verbose:
            print(f"Using model: {model}")

        return LLM(
            model=model,
            api_base=api_base,
            api_key=self.api_key,
            timeout=self.timeout,
        )
```

**Why this is required**: This method handles model configuration, API authentication, and DataRobot LLM Gateway integration. Changing it will break deployment.

#### `agents` Property
Defines the list of sub-agents

```python
@property
def agents(self) -> List[Agent]:
        return [self.agent_1, self.agent_2]
```

#### `tasks` Property
Defines the list of tasks for the sub-agents

```python
@property
def tasks(self) -> List[Task]:
        return [self.task_1, self.task_2]
```


### 4. Agent tools

**IMPORTANT**: Add required tools in the `agent_retrieval_agent/agent` directory. Do not add/modify any files outside of this directory. If some of the tools require adding new packages, they should be added to the pyproject.toml and properly installed using command

```shell
dr task run agent_retrieval_agent:install
```

**IMPORTANT**: Tools must be imported and used in `MyAgent` implementation.


### 5. Preferred LLM model

Preferred model should be set using ```self.model = "{preferred_model_here}"``` which will then be read in each ```self.llm()``` invocation.
**Important**: `self.model` parameter must be prefixed with `datarobot/`.

## Agent Testing

Review and update the tests in the `agent_retrieval_agent/tests` directory after code changes were made to the agent.
Run the following shell commands to run the tests:

```shell
dr task run agent_retrieval_agent:lint
```

```shell
dr task run agent_retrieval_agent:test
```

## Post Deployment Validation

Run the following shell command to validate the agent after deployment. If the response has no errors then the deployment is successful.

```shell
task agent:cli -- execute-deployment --user_prompt "Agent specific prompt to validate that it's working" --deployment_id <deployment_id>
```
