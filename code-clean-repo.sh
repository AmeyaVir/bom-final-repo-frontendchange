#!/bin/bash

# Define the name of the output zip file
OUTPUT_ZIP="code_repo_clean.zip"

# Define the root directory of your code repository
# Change this to the actual path of your repository
REPO_ROOT="." 

# Exclude patterns:
# - .env: Environment variable files
# - *.bak: Common backup file extension
# - *~: Editor backup files (e.g., Emacs)
# - *.tmp: Temporary files
# - *.log: Log files
# - .DS_Store: macOS specific metadata file
# - Thumbs.db: Windows specific thumbnail cache file
# - *.zone.identifier: Windows security zone information
EXCLUDE_PATTERNS=(
    "*.env"
    "*.bak"
    "*_bk*"
    "*~"
    "*.tmp"
    "*.log"
    ".DS_Store"
    "Thumbs.db"
    "*.zone.identifier"
    "*:Zone.Identifier"
    "code_repo_clean_v1/*"
    "*/uploads/*"
    "*node_modules/*" # Example: exclude node_modules for JavaScript projects
    "*/__pycache__/*" # Exclude all __pycache__ directories
    "*/venv/*" # Exclude the entire venv directory
    "*.mypy_cache/*" # Exclude the top-level mypy cache directory
    "*/.mypy_cache/*" # Exclude mypy's cache directory in subfolders
    "*.json*"
)

# Construct the exclude arguments for the zip command
EXCLUDE_ARGS=""
for pattern in "${EXCLUDE_PATTERNS[@]}"; do
    EXCLUDE_ARGS+=" -x \"$pattern\""
done

# Create the zip archive, excluding specified patterns
# The -r flag is for recursive zipping of directories
# The eval command is used to correctly interpret the EXCLUDE_ARGS string
eval "zip -r \"$OUTPUT_ZIP\" \"$REPO_ROOT\" $EXCLUDE_ARGS"

echo "Repository successfully zipped to '$OUTPUT_ZIP' excluding specified files."
