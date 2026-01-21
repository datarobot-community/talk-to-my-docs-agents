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


import hashlib
from pathlib import Path
from typing import List

import pulumi_command as command
from datarobot_pulumi_utils.pulumi.stack import PROJECT_NAME

project_dir = Path(__file__).parent.parent.parent


def _frontend_triggers(frontend_dir: Path) -> List[str]:
    """Generate a deterministic trigger hash based on lockfile and source mtimes."""

    hasher = hashlib.sha256()
    relevant_paths = []

    for relative_path in [
        "package-lock.json",
        "package.json",
        "index.html",
        "components.json",
        "vite.config.ts",
        "tailwind.config.js",
        ".npmrc",
    ]:
        candidate = frontend_dir / relative_path
        if candidate.exists():
            relevant_paths.append(candidate)

    tsconfig_paths = sorted(
        path for path in frontend_dir.glob("tsconfig.*") if path.is_file()
    )
    relevant_paths.extend(tsconfig_paths)

    src_dir = frontend_dir / "src"
    if src_dir.exists():
        relevant_paths.extend(
            sorted(path for path in src_dir.rglob("*") if path.is_file())
        )

    public_dir = frontend_dir / "public"
    if public_dir.exists():
        relevant_paths.extend(
            sorted(path for path in public_dir.rglob("*") if path.is_file())
        )

    for path in relevant_paths:
        if not path.exists():
            continue
        relative_path = path.relative_to(frontend_dir).as_posix()
        hasher.update(relative_path.encode())
        hasher.update(str(path.stat().st_mtime_ns).encode())

    digest = hasher.hexdigest()
    return [digest]


def build_frontend() -> command.local.Command:
    """
    Build the frontend application before deploying infrastructure.
    Split into two stages: install dependencies and build application.
    """
    frontend_dir = project_dir / "frontend_web"

    build_command = " && ".join(
        [
            f"cd {frontend_dir}",
            "npm ci",
            "npm run build",
        ]
    )

    build_react_app = command.local.Command(
        f"Talk to My Docs [{PROJECT_NAME}] Build Frontend",
        create=build_command,
        triggers=_frontend_triggers(frontend_dir),
    )

    return build_react_app


frontend_web = build_frontend()

__all__ = ["frontend_web"]
