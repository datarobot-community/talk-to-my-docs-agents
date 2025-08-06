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
"""
Core document processor module. This is where we convert, extract, and store metadata about documents
for passing around to LLMs and agents.
"""

from .constants import SUPPORTED_FILE_TYPES, SUPPORTED_MIME_TYPES
from .document_loader import convert_document_to_text
from .exceptions import (
    DocProcessorError,
    DocProcessorNoExtractorError,
    DocProcessorUnsupportedFileTypeError,
)
from .image_loader import convert_document_pages_to_images

__all__ = [
    "SUPPORTED_FILE_TYPES",
    "SUPPORTED_MIME_TYPES",
    "convert_document_to_text",
    "convert_document_pages_to_images",
    "DocProcessorError",
    "DocProcessorNoExtractorError",
    "DocProcessorUnsupportedFileTypeError",
]
