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
from typing import Sequence

from datarobot.core.config import DataRobotAppFrameworkBaseSettings
from pydantic import Field, ValidationInfo, field_validator

from app.auth.oauth import OAuthImpl
from app.telemetry.enums import FormatType, LogLevel


class Config(DataRobotAppFrameworkBaseSettings):
    datarobot_endpoint: str
    datarobot_api_token: str

    llm_deployment_id: str | None = None
    use_datarobot_llm_gateway: bool = False
    llm_default_model: str = "custom-model"
    llm_default_model_friendly_name: str = "DataRobot LLM Blueprint"
    agent_retrieval_agent_deployment_id: str = ""

    oauth_impl: OAuthImpl = OAuthImpl.DATAROBOT
    datarobot_oauth_providers: Sequence[str] = ()

    google_client_id: str | None = None
    google_client_secret: str | None = None

    box_client_id: str | None = None
    box_client_secret: str | None = None

    # SharePoint/Azure OAuth configuration
    sharepoint_client_id: str | None = None
    sharepoint_client_secret: str | None = None
    sharepoint_tenant_id: str | None = None

    session_secret_key: str
    session_max_age: int = 14 * 24 * 60 * 60  # 14 days, in seconds
    session_https_only: bool = True
    session_cookie_name: str = "sess"  # Can be overridden for different apps

    # these two configs should help to emulate the DataRobot Custom App Authentication like in a deployment application but locally,
    # so you can assume the user and be able to open the UI in the browser without any other configurations.
    # If both are set at the same time, only the DR API key will be used to authenticate the user.
    test_user_api_key: str | None = None
    test_user_email: str | None = None

    database_uri: str = "sqlite+aiosqlite:///.data/database.sqlite"

    storage_path: str = ".data/storage"

    # Feature flag for semantic retrieval via DataRobot's managed Memory API.
    # Default OFF: the feature ships dark and the app uses the legacy
    # keyword/full-content path until enabled. Requires memory_space_id.
    vdb_enabled: bool = False
    # Default retrieval mode for NEW knowledge bases when the feature is enabled
    # ("semantic" or "keyword"). Existing KBs keep their stored mode.
    vdb_default_retrieval_mode: str = "semantic"

    # Indexing guards: skip files larger than this and cap files per build. A KB
    # stuck "indexing" past the reaper threshold (e.g. a process restart) is reset
    # to failed on startup.
    vdb_max_file_mb: int = 25
    vdb_max_files: int = 200
    vdb_stuck_index_minutes: int = 30

    # Client-side chunking before storing to the Memory API (the service stores
    # what we send; it does not chunk). Larger chunks mean fewer embeds (faster
    # indexing) at a small retrieval-granularity cost.
    #
    # Bounded below: the sliding window advances by (chunk_chars - overlap), so a
    # tiny chunk size or an overlap at or above it would step one character at a
    # time and emit ~one chunk per character of a long paragraph, each an embedded
    # HTTP round-trip. Rejected at startup rather than clamped silently, so a
    # costly misconfiguration is loud.
    vdb_chunk_chars: int = Field(default=2000, ge=100)
    vdb_chunk_overlap_chars: int = Field(default=150, ge=0)

    # Indexing throughput knobs. Chunks are added in batches of vdb_add_batch_size
    # messages per request, run vdb_index_concurrency requests at a time.
    # IMPORTANT: the Memory API 500s under heavy concurrent writes (measured: a
    # large KB at concurrency 10 fails a 500-storm; concurrency 6 completes). Keep
    # concurrency conservative; the bigger reliable win is fewer chunks (larger
    # vdb_chunk_chars) and, later, incremental re-indexing. Tunable so ops can
    # raise it only against a Memory API deployment that tolerates it.
    vdb_index_concurrency: int = 6
    # Up to 100 chunks per add request (the service stores each message as a
    # separate memory and caps at 100/call). Bigger batches = fewer round-trips;
    # this is the safe throughput lever (concurrency is not).
    vdb_add_batch_size: int = 100

    # --- DataRobot Memory API (the only retrieval backend) ---
    # Memory space id (required for retrieval to be active).
    memory_space_id: str | None = None
    # Per-KB identity scope for stored chunks: f"{prefix}{kb_id}".
    memory_user_prefix: str = "kb-"
    # Top-k for document retrieval (service caps this at 50).
    memory_top_k: int = 10
    # Cross-session agent memory (recall + store user turns via the Memory API).
    # Requires memory_space_id; independent of the retrieval backend.
    chat_memory_enabled: bool = False
    chat_memory_top_k: int = 5

    log_level: LogLevel = LogLevel.INFO
    log_format: FormatType = "text"

    otel_entity_id: str = ""
    otel_exporter_otlp_endpoint: str = ""
    otel_exporter_otlp_headers: str = ""
    otel_sdk_disabled: bool = False
    profiling_enabled: bool = False

    @field_validator("otel_exporter_otlp_headers", mode="before")
    @classmethod
    def _assemble_otel_headers(cls, v: object, info: ValidationInfo) -> object:
        if v:
            return v
        entity_id = (info.data or {}).get("otel_entity_id", "")
        api_token = (info.data or {}).get("datarobot_api_token", "") or os.environ.get(
            "DATAROBOT_API_TOKEN", ""
        )
        if entity_id and api_token:
            return f"x-datarobot-entity-id={entity_id},x-datarobot-api-key={api_token}"
        return v

    @field_validator("otel_sdk_disabled", mode="before")
    @classmethod
    def _coerce_empty_string(cls, v: object) -> object:
        return False if v == "" else v

    @field_validator("vdb_chunk_overlap_chars")
    @classmethod
    def _overlap_below_chunk_size(cls, v: int, info: ValidationInfo) -> int:
        """Reject an overlap that would stall the chunking window.

        chunk_chars is validated first (field order), so it is available here. An
        overlap at or above the chunk size makes the window advance by one
        character, turning a single long paragraph into one chunk per character.
        """
        chunk_chars = (info.data or {}).get("vdb_chunk_chars")
        if isinstance(chunk_chars, int) and v >= chunk_chars:
            raise ValueError(
                f"vdb_chunk_overlap_chars ({v}) must be smaller than "
                f"vdb_chunk_chars ({chunk_chars})"
            )
        return v
