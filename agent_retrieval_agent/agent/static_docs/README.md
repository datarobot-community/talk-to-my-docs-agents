# Static Documents

This directory serves as a **fallback document source** for the file search tool.

When no knowledge base or uploaded files are available, the agent will search and read documents
placed in this directory.

## How to use

1. Place any documents you want the agent to always have access to in this directory.
2. Supported formats include PDF, DOCX, PPTX, TXT, and Markdown files.
3. Subdirectories are supported — files are discovered recursively.

> **Note:** This `static_docs/README.md` file is excluded from the agent's document search automatically.
