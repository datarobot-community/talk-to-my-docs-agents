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
from pathlib import Path

import pytest

from core.document_loader import convert_document_to_text


def test_convert_markdown_to_text(shared_datadir: Path) -> None:
    doc = shared_datadir / "sample_documents" / "developer" / "sample_yaml_spec.md"
    text = convert_document_to_text(str(doc))
    assert "The presence of this file presumes your repository" in text[1]


@pytest.mark.parametrize(
    "doc_name, first_page, second_page",
    [
        ("sample_tech_spec.pdf", 1, 5),
        ("sample_tech_spec.docx", 1, 1),
    ],
)
def test_convert_spec_to_text(
    shared_datadir: Path, doc_name: str, first_page: int, second_page: int
) -> None:
    doc = shared_datadir / "sample_documents" / "developer" / doc_name
    text = convert_document_to_text(str(doc))
    assert "large amounts of feedback from users" in text[first_page]
    assert "This would involve having the nginx" in text[second_page]
