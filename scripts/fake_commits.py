#!/usr/bin/env python3
"""
Script to artificially inflate Git commit history.
WARNING: This is for educational purposes only. Falsifying commit history
may violate platform terms of service and is not recommended for professional use.
"""

import subprocess
import random
from datetime import datetime, timedelta
import os

def run_git_command(command: str):
    """Run a git command."""
    result = subprocess.run(command.split(), capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
    return result.returncode == 0

def create_fake_commits(num_commits: int = 50, days_back: int = 365):
    """
    Create fake commits spread over the last 'days_back' days.
    """
    base_date = datetime.now() - timedelta(days=days_back)

    for i in range(num_commits):
        # Random date within the period
        random_days = random.randint(0, days_back)
        commit_date = base_date + timedelta(days=random_days)

        # Format for GIT_AUTHOR_DATE and GIT_COMMITTER_DATE
        date_str = commit_date.strftime("%Y-%m-%d %H:%M:%S")

        # Create a small change (add a comment to a file)
        with open("fake_activity.txt", "a") as f:
            f.write(f"Fake commit {i+1} on {date_str}\n")

        # Stage and commit with fake date
        run_git_command("git add fake_activity.txt")
        env = os.environ.copy()
        env["GIT_AUTHOR_DATE"] = date_str
        env["GIT_COMMITTER_DATE"] = date_str
        subprocess.run(["git", "commit", "-m", f"Fake commit {i+1}"], env=env)

    print(f"Created {num_commits} fake commits.")

if __name__ == "__main__":
    # Example: 100 commits over last 365 days
    create_fake_commits(100, 365)
    print("Run 'git push' to upload to remote.")