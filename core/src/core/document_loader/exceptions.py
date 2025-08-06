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
"""Exceptions for easier error handling within document loading"""


class DocProcessorError(Exception):
    """Base class for all exceptions raised by the DocProcessor."""

    pass


class DocProcessorNoExtractorError(DocProcessorError):
    """Raised when no extractor is found for the given file type."""

    def __init__(self, file_type: str):
        super().__init__(f"No extractor found for file type: {file_type}")
        self.file_type = file_type


class DocProcessorUnsupportedFileTypeError(DocProcessorError):
    """Raised when an unsupported file type is encountered."""

    def __init__(self, file_type: str):
        super().__init__(f"Unsupported file type: {file_type}")
        self.file_type = file_type
