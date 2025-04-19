#!/bin/bash

# Exit on error
set -e

# Check and update remote URL if needed
CURRENT_REMOTE=$(git remote get-url origin)
read -p "Current remote URL: $CURRENT_REMOTE. Is this correct? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    read -p "Enter new remote URL: " NEW_REMOTE
    git remote set-url origin "$NEW_REMOTE"
    echo "Remote URL updated to: $NEW_REMOTE"
fi

# Get list of changed files
CHANGED_FILES=$(git status --porcelain | awk '{print $2}')

if [ -z "$CHANGED_FILES" ]; then
    echo "No changes detected"
    exit 0
fi

# Add all changed files
echo "Adding changed files:"
echo "$CHANGED_FILES"
git add $CHANGED_FILES

# Get commit message
read -p "Enter commit message: " COMMIT_MSG

# Commit changes
git commit -m "$COMMIT_MSG"

# Push to remote using git directly
echo "Pushing changes..."
git push origin main

echo "Changes pushed successfully" 