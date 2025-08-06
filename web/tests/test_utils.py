# Copyright 2025 DataRobot, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pytest
from _pytest.monkeypatch import MonkeyPatch

from app import get_app_base_url


@pytest.mark.parametrize(
    "base_path, notebook_id, api_port, expected",
    [
        ("custom_applications/testId", "", "8080", "/custom_applications/testId/"),
        (
            "/custom_applications/testId",
            "notebookId",
            "8080",
            "/custom_applications/testId/",
        ),
        ("", "notebookId", "8080", "/notebook-sessions/notebookId/ports/8080/"),
        ("", "", "8080", "/"),
        (
            None,
            "notebookId",
            "8080",
            "/notebook-sessions/notebookId/ports/8080/",
        ),
        (None, None, "8080", "/"),
    ],
)
def test_get_app_base_url(
    monkeypatch: MonkeyPatch,
    base_path: str | None,
    notebook_id: str | None,
    api_port: str,
    expected: str,
) -> None:
    if base_path is not None:
        monkeypatch.setenv("BASE_PATH", base_path)
    else:
        monkeypatch.delenv("BASE_PATH", raising=False)
    if notebook_id is not None:
        monkeypatch.setenv("NOTEBOOK_ID", notebook_id)
    else:
        monkeypatch.delenv("NOTEBOOK_ID", raising=False)

    result = get_app_base_url(api_port)
    assert result == expected
