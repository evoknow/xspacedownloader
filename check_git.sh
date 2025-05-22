#!/bin/bash
echo "Checking for git..."
which git
echo "Current directory:"
pwd
echo "Is .git directory present?"
if [ -d .git ]; then
    echo "Yes, .git directory exists"
    echo "Current branch:"
    git branch
else
    echo "No, .git directory does not exist"
fi