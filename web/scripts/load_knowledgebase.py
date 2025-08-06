#!/usr/bin/env python3
# /// script
# dependencies = [
#     "httpx>=0.25.0",
# ]
# ///
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
UV script to upload files from a local folder to create a knowledge base.

This script creates a knowledge base and uploads files from a local directory
to populate it with actual file records and content.

Usage:
    uv run load_knowledgebase.py --app-url http://localhost:5173 \
                        --api-token your-bearer-token \
                        --base-name "My Knowledge Base" \
                        --base-description "Description of the base" \
                        --source-path /path/to/documents \
                        --base-path "custom/base/path"
"""

import argparse
import asyncio
import json
import logging
import mimetypes
import sys
from pathlib import Path
from typing import Any, List

import httpx

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Supported file extensions (matching the core document loader)
SUPPORTED_EXTENSIONS = {
    "pdf",
    "docx",
    "pptx",
    "txt",
    "md",
    "csv",
}


class KnowledgeBaseCreator:
    """Creates knowledge bases and file records using the API."""

    def __init__(self, app_url: str, api_token: str):
        self.app_url = app_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self.client = httpx.AsyncClient(timeout=60.0)

    async def __aenter__(self) -> "KnowledgeBaseCreator":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.client.aclose()

    async def create_knowledge_base(
        self, title: str, description: str, knowledge_base_path: str | None = None
    ) -> Any:
        """Create a new knowledge base."""
        url = f"{self.app_url}/api/v1/knowledge-bases/"

        payload = {
            "title": title,
            "description": description,
        }

        # Add custom base path if provided
        if knowledge_base_path:
            payload["path"] = knowledge_base_path

        logger.info(f"Creating knowledge base: {title}")

        response = await self.client.post(url, json=payload, headers=self.headers)

        if response.status_code != 200:
            raise Exception(
                f"Failed to create base: {response.status_code} - {response.text}"
            )

        knowledge_base_data = response.json()
        logger.info(f"Created knowledge base with UUID: {knowledge_base_data['uuid']}")
        return knowledge_base_data

    async def upload_file(self, file_path: Path, knowledge_base_uuid: str) -> Any:
        """Upload a file to the knowledge base."""
        url = f"{self.app_url}/api/v1/files/local/upload"

        # Prepare the file for upload
        try:
            # Read the file content first
            file_content = file_path.read_bytes()

            # Guess the MIME type
            mime_type = (
                mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
            )

            # Prepare files for multipart upload
            files = {"files": (file_path.name, file_content, mime_type)}

            # Create headers without Content-Type (let httpx set it for multipart)
            headers = {
                "Authorization": self.headers["Authorization"],
                "Accept": self.headers["Accept"],
            }

            params = (
                {"knowledge_base_uuid": knowledge_base_uuid}
                if knowledge_base_uuid
                else {}
            )

            logger.info(f"Uploading file: {file_path.name} ({len(file_content)} bytes)")

            response = await self.client.post(
                url, files=files, headers=headers, params=params
            )

        except Exception as e:
            logger.error(f"Failed to read file {file_path.name}: {e}")
            return {
                "filename": file_path.name,
                "error": f"Failed to read file: {str(e)}",
            }

        if response.status_code != 200:
            logger.error(
                f"Failed to upload file {file_path.name}: {response.status_code} - {response.text}"
            )
            return {
                "filename": file_path.name,
                "error": f"HTTP {response.status_code}: {response.text}",
            }

        result = response.json()

        # The upload endpoint returns a list, get the first (and only) result
        if isinstance(result, list) and len(result) > 0:
            upload_result = result[0]
            if "error" in upload_result:
                logger.error(
                    f"Upload failed for {file_path.name}: {upload_result['error']}"
                )
                return {
                    "filename": file_path.name,
                    "error": upload_result["error"],
                }
            else:
                logger.info(f"Successfully uploaded file: {file_path.name}")
                return upload_result
        else:
            logger.error(f"Unexpected response format for {file_path.name}: {result}")
            return {
                "filename": file_path.name,
                "error": "Unexpected response format",
            }

    def get_supported_files(self, source_path: Path) -> List[Path]:
        """Get all supported files from the source directory."""
        supported_files = []

        if not source_path.exists():
            raise FileNotFoundError(f"Source path does not exist: {source_path}")

        if not source_path.is_dir():
            raise ValueError(f"Source path is not a directory: {source_path}")

        for file_path in source_path.rglob("*"):
            if file_path.is_file():
                extension = file_path.suffix.lower().lstrip(".")
                if extension in SUPPORTED_EXTENSIONS:
                    supported_files.append(file_path)
                else:
                    logger.debug(f"Skipping unsupported file: {file_path}")

        logger.info(f"Found {len(supported_files)} supported files in {source_path}")
        return supported_files

    async def upload_knowledge_base_files(
        self,
        title: str,
        description: str,
        source_path: Path,
        knowledge_base_path: str | None = None,
        max_concurrent_uploads: int = 5,
    ) -> Any:
        """Create a knowledge base and upload all files from the source directory."""

        # Create the knowledge base
        knowledge_base_data = await self.create_knowledge_base(
            title, description, knowledge_base_path
        )
        knowledge_base_uuid = knowledge_base_data["uuid"]

        # Get all supported files
        files_to_process = self.get_supported_files(source_path)

        if not files_to_process:
            logger.warning("No supported files found to process")
            return {
                "knowledge_base": knowledge_base_data,
                "files": [],
                "summary": {"total": 0, "successful": 0, "failed": 0},
            }

        # Upload files with concurrency control
        semaphore = asyncio.Semaphore(max_concurrent_uploads)

        async def upload_with_semaphore(file_path: Path) -> Any:
            async with semaphore:
                return await self.upload_file(file_path, knowledge_base_uuid)

        logger.info(f"Starting upload of {len(files_to_process)} files...")
        upload_results = await asyncio.gather(
            *[upload_with_semaphore(file_path) for file_path in files_to_process],
            return_exceptions=True,
        )

        # Process results
        successful_uploads = []
        failed_uploads = []

        for i, result in enumerate(upload_results):
            if isinstance(result, Exception):
                failed_uploads.append(
                    {"filename": files_to_process[i].name, "error": str(result)}
                )
            elif isinstance(result, dict) and "error" in result:
                failed_uploads.append(result)
            else:
                successful_uploads.append(result)

        summary = {
            "total": len(files_to_process),
            "successful": len(successful_uploads),
            "failed": len(failed_uploads),
        }

        logger.info(
            f"Upload complete: {summary['successful']}/{summary['total']} files uploaded successfully"
        )

        if failed_uploads:
            logger.warning(f"Failed uploads: {len(failed_uploads)}")
            for failed in failed_uploads:
                logger.warning(f"  - {failed['filename']}: {failed['error']}")

        return {
            "base": knowledge_base_data,
            "successful_files": successful_uploads,
            "failed_files": failed_uploads,
            "summary": summary,
        }


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a knowledge base and populate it with file records from a directory"
    )
    parser.add_argument(
        "--app-url",
        required=True,
        help="Base URL of the application (e.g., http://localhost:5173)",
    )
    parser.add_argument(
        "--api-token", required=True, help="Bearer token for API authentication"
    )
    parser.add_argument(
        "--base-name", required=True, help="Name/title for the knowledge base"
    )
    parser.add_argument(
        "--base-description", required=True, help="Description for the knowledge base"
    )
    parser.add_argument(
        "--source-path",
        required=True,
        help="Path to the directory containing files to register",
    )
    parser.add_argument(
        "--base-path",
        help="Custom base path for the knowledge base (optional, will auto-generate if not provided)",
    )
    parser.add_argument(
        "--max-concurrent-uploads",
        type=int,
        default=5,
        help="Maximum number of concurrent file uploads (default: 5)",
    )
    parser.add_argument(
        "--output-file", help="File to save the creation results as JSON (optional)"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate source path
    source_path = Path(args.source_path)
    if not source_path.exists():
        logger.error(f"Source path does not exist: {source_path}")
        sys.exit(1)

    if not source_path.is_dir():
        logger.error(f"Source path is not a directory: {source_path}")
        sys.exit(1)

    try:
        async with KnowledgeBaseCreator(args.app_url, args.api_token) as creator:
            result = await creator.upload_knowledge_base_files(
                title=args.base_name,
                description=args.base_description,
                source_path=source_path,
                knowledge_base_path=args.base_path,
                max_concurrent_uploads=args.max_concurrent_uploads,
            )

            # Print summary
            print("\n" + "=" * 60)
            print("KNOWLEDGE BASE CREATION SUMMARY")
            print("=" * 60)
            print(f"Base Name: {result['base']['title']}")
            print(f"Base UUID: {result['base']['uuid']}")
            print(f"Base Path: {result['base']['path']}")
            print(
                f"Files Uploaded: {result['summary']['successful']}/{result['summary']['total']}"
            )

            if result["failed_files"]:
                print(f"\nFailed File Uploads ({len(result['failed_files'])}):")
                for failed in result["failed_files"]:
                    print(f"  - {failed['filename']}: {failed['error']}")

            # Save results to file if requested
            if args.output_file:
                with open(args.output_file, "w") as f:
                    json.dump(result, f, indent=2, default=str)
                print(f"\nResults saved to: {args.output_file}")

            print("=" * 60)
            print("NOTE: Files uploaded and stored in the knowledge base.")
            print("=" * 60)

            # Exit with error code if any uploads failed
            if result["failed_files"]:
                sys.exit(1)

    except Exception as e:
        logger.error(f"Failed to create knowledge base: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
