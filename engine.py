#!/usr/bin/env python3
"""
engine.py - Core Engine for GitHub Historical Contribution Graph Automation.

Handles:
- Configurable per-year density schedules (2019 - 2026)
- Daily randomized commit calculations with weekend weighting
- Historical commit execution with backdated GIT_AUTHOR_DATE & GIT_COMMITTER_DATE
- Git hook bypass (--no-verify)
- Safe history reset with automated backup tags
- Remote force-push orchestration
"""

import os
import sys
import json
import time
import random
import subprocess
from datetime import datetime, date, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Any, Callable

# Standard GitHub contribution colors (dark mode)
GITHUB_LEVEL_COLORS = [
    "#161b22",  # 0 commits
    "#0e4429",  # 1-2 commits
    "#006d32",  # 3-4 commits
    "#26a641",  # 5-6 commits
    "#39d353"   # 7+ commits
]

PRESET_CONFIGS = {
    "progressive": {
        "description": "Gradual ramp-up: sparse in 2019, steadily growing to heavy green in 2026.",
        "weekend_weight": 0.35,
        "years": {
            2019: {"active_day_pct": 25, "min_commits": 1, "max_commits": 2},
            2020: {"active_day_pct": 35, "min_commits": 1, "max_commits": 3},
            2021: {"active_day_pct": 45, "min_commits": 1, "max_commits": 3},
            2022: {"active_day_pct": 58, "min_commits": 2, "max_commits": 4},
            2023: {"active_day_pct": 70, "min_commits": 2, "max_commits": 5},
            2024: {"active_day_pct": 80, "min_commits": 2, "max_commits": 6},
            2025: {"active_day_pct": 88, "min_commits": 3, "max_commits": 7},
            2026: {"active_day_pct": 92, "min_commits": 3, "max_commits": 8},
        }
    },
    "natural": {
        "description": "Realistic engineer profile: weekday clusters, weekend dips, and occasional sprint bursts.",
        "weekend_weight": 0.20,
        "years": {
            2019: {"active_day_pct": 40, "min_commits": 1, "max_commits": 3},
            2020: {"active_day_pct": 50, "min_commits": 1, "max_commits": 4},
            2021: {"active_day_pct": 60, "min_commits": 2, "max_commits": 4},
            2022: {"active_day_pct": 65, "min_commits": 2, "max_commits": 5},
            2023: {"active_day_pct": 75, "min_commits": 2, "max_commits": 5},
            2024: {"active_day_pct": 78, "min_commits": 2, "max_commits": 6},
            2025: {"active_day_pct": 82, "min_commits": 3, "max_commits": 6},
            2026: {"active_day_pct": 85, "min_commits": 3, "max_commits": 7},
        }
    },
    "intense": {
        "description": "Solid green wall: prolific output across all years with dense multi-commit days.",
        "weekend_weight": 0.65,
        "years": {
            2019: {"active_day_pct": 80, "min_commits": 3, "max_commits": 7},
            2020: {"active_day_pct": 85, "min_commits": 3, "max_commits": 8},
            2021: {"active_day_pct": 88, "min_commits": 4, "max_commits": 8},
            2022: {"active_day_pct": 90, "min_commits": 4, "max_commits": 9},
            2023: {"active_day_pct": 92, "min_commits": 4, "max_commits": 9},
            2024: {"active_day_pct": 94, "min_commits": 5, "max_commits": 10},
            2025: {"active_day_pct": 95, "min_commits": 5, "max_commits": 10},
            2026: {"active_day_pct": 96, "min_commits": 5, "max_commits": 10},
        }
    },
    "steady": {
        "description": "Consistent cadence: steady 60-70% active days year-over-year.",
        "weekend_weight": 0.30,
        "years": {
            2019: {"active_day_pct": 60, "min_commits": 2, "max_commits": 4},
            2020: {"active_day_pct": 62, "min_commits": 2, "max_commits": 4},
            2021: {"active_day_pct": 65, "min_commits": 2, "max_commits": 5},
            2022: {"active_day_pct": 68, "min_commits": 2, "max_commits": 5},
            2023: {"active_day_pct": 70, "min_commits": 2, "max_commits": 5},
            2024: {"active_day_pct": 72, "min_commits": 2, "max_commits": 5},
            2025: {"active_day_pct": 75, "min_commits": 2, "max_commits": 6},
            2026: {"active_day_pct": 78, "min_commits": 2, "max_commits": 6},
        }
    },
    "minimalist": {
        "description": "Subtle activity: light sprinkle of commits throughout the years.",
        "weekend_weight": 0.15,
        "years": {
            2019: {"active_day_pct": 20, "min_commits": 1, "max_commits": 2},
            2020: {"active_day_pct": 25, "min_commits": 1, "max_commits": 2},
            2021: {"active_day_pct": 30, "min_commits": 1, "max_commits": 2},
            2022: {"active_day_pct": 35, "min_commits": 1, "max_commits": 2},
            2023: {"active_day_pct": 40, "min_commits": 1, "max_commits": 3},
            2024: {"active_day_pct": 45, "min_commits": 1, "max_commits": 3},
            2025: {"active_day_pct": 50, "min_commits": 1, "max_commits": 3},
            2026: {"active_day_pct": 55, "min_commits": 1, "max_commits": 4},
        }
    }
}

COMMIT_MESSAGES = [
    "feat: refine data pipeline routines",
    "fix: handle boundary condition in parser",
    "docs: update architecture references",
    "perf: optimize memory footprint during batch ingest",
    "chore: dependency maintenance and cleanup",
    "refactor: modularize configuration utilities",
    "style: format code according to style conventions",
    "test: add unit coverage for date transform modules",
    "build: tune compilation scripts and toolchain",
    "ci: update automated test workflow matrix",
    "feat: add telemetry hooks for sync status",
    "fix: resolve race condition in cache invalidation",
    "docs: enhance code comments and setup guide",
    "perf: accelerate index lookup algorithms",
    "refactor: extract reusable helper components",
    "chore: prune stale assets and logs"
]


class ContributionEngine:
    """Core automation engine for GitHub contribution graph creation."""

    def __init__(self, repo_path: str = "."):
        self.repo_path = os.path.abspath(repo_path)

    def run_git(self, args: List[str], env: Optional[Dict[str, str]] = None) -> Tuple[int, str, str]:
        """Runs a git command inside the target repo."""
        current_env = os.environ.copy()
        if env:
            current_env.update(env)
        p = subprocess.run(
            ["git"] + args,
            cwd=self.repo_path,
            env=current_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return p.returncode, p.stdout.strip(), p.stderr.strip()

    def get_git_info(self) -> Dict[str, Any]:
        """Inspects and returns current git repo metadata."""
        is_repo = os.path.isdir(os.path.join(self.repo_path, ".git"))
        if not is_repo:
            return {"is_git_repo": False, "repo_path": self.repo_path}

        _, branch, _ = self.run_git(["branch", "--show-current"])
        _, remote_url, _ = self.run_git(["config", "--get", "remote.origin.url"])
        _, user_name, _ = self.run_git(["config", "--get", "user.name"])
        _, user_email, _ = self.run_git(["config", "--get", "user.email"])
        _, commit_count_str, _ = self.run_git(["rev-list", "--count", "HEAD"])
        _, last_commit, _ = self.run_git(["log", "-1", "--format=%cd (%cr)", "--date=iso"])

        try:
            commit_count = int(commit_count_str)
        except ValueError:
            commit_count = 0

        # Check for active hooks
        hooks_dir = os.path.join(self.repo_path, ".git", "hooks")
        active_hooks = []
        if os.path.isdir(hooks_dir):
            for fname in os.listdir(hooks_dir):
                if not fname.endswith(".sample"):
                    fpath = os.path.join(hooks_dir, fname)
                    if os.access(fpath, os.X_OK):
                        active_hooks.append(fname)

        return {
            "is_git_repo": True,
            "repo_path": self.repo_path,
            "branch": branch or "main",
            "remote_url": remote_url,
            "user_name": user_name or "Unknown",
            "user_email": user_email or "unknown@example.com",
            "commit_count": commit_count,
            "last_commit": last_commit,
            "active_hooks": active_hooks
        }

    def set_author(self, name: str, email: str) -> bool:
        """Sets local repository author details."""
        code1, _, _ = self.run_git(["config", "user.name", name])
        code2, _, _ = self.run_git(["config", "user.email", email])
        return code1 == 0 and code2 == 0

    @staticmethod
    def get_intensity_level(commits: int) -> int:
        """Maps commit count to GitHub's 5 intensity tiers (0 to 4)."""
        if commits <= 0:
            return 0
        elif commits <= 2:
            return 1
        elif commits <= 4:
            return 2
        elif commits <= 6:
            return 3
        else:
            return 4

    def simulate(
        self,
        year_configs: Dict[int, Dict[str, Any]],
        start_date: date = date(2019, 1, 1),
        end_date: Optional[date] = None,
        weekend_weight: float = 0.35,
        random_seed: Optional[int] = 42
    ) -> Dict[str, Any]:
        """
        Simulates the entire historical commit plan from start_date to end_date.
        Returns detailed stats and daily schedule without writing to Git.
        """
        if end_date is None:
            # Default to present day (2026-10-12)
            end_date = date(2026, 10, 12)

        rng = random.Random(random_seed)
        calendar = []
        year_stats: Dict[int, Dict[str, Any]] = {}
        total_commits = 0
        total_active_days = 0
        current_streak = 0
        max_streak = 0
        busiest_day = {"date": "", "commits": 0}

        # Initialize year_stats
        cur_year = start_date.year
        while cur_year <= end_date.year:
            year_stats[cur_year] = {
                "year": cur_year,
                "total_days": 0,
                "active_days": 0,
                "total_commits": 0,
                "level_counts": [0, 0, 0, 0, 0]
            }
            cur_year += 1

        curr = start_date
        while curr <= end_date:
            y = curr.year
            y_cfg = year_configs.get(y, {"active_day_pct": 50, "min_commits": 1, "max_commits": 4})
            is_weekend = curr.weekday() in (5, 6)

            base_chance = float(y_cfg.get("active_day_pct", 50)) / 100.0
            day_chance = base_chance * (weekend_weight if is_weekend else 1.0)
            day_chance = max(0.0, min(1.0, day_chance))

            is_active = rng.random() < day_chance
            day_commits = 0
            if is_active:
                min_c = int(y_cfg.get("min_commits", 1))
                max_c = int(y_cfg.get("max_commits", 3))
                if max_c < min_c:
                    max_c = min_c
                # Weighted distribution toward lower-mid in the range with occasional spikes
                day_commits = rng.randint(min_c, max_c)

            level = self.get_intensity_level(day_commits)
            color = GITHUB_LEVEL_COLORS[level]

            day_entry = {
                "date": curr.strftime("%Y-%m-%d"),
                "year": y,
                "month": curr.month,
                "day": curr.day,
                "weekday": curr.weekday(),  # 0=Mon, 6=Sun
                "is_weekend": is_weekend,
                "commits": day_commits,
                "level": level,
                "color": color
            }
            calendar.append(day_entry)

            # Update stats
            total_commits += day_commits
            if day_commits > 0:
                total_active_days += 1
                current_streak += 1
                if current_streak > max_streak:
                    max_streak = current_streak
                if day_commits > busiest_day["commits"]:
                    busiest_day = {"date": day_entry["date"], "commits": day_commits}
            else:
                current_streak = 0

            if y in year_stats:
                year_stats[y]["total_days"] += 1
                if day_commits > 0:
                    year_stats[y]["active_days"] += 1
                year_stats[y]["total_commits"] += day_commits
                year_stats[y]["level_counts"][level] += 1

            curr += timedelta(days=1)

        total_days = len(calendar)
        activity_percentage = round((total_active_days / total_days * 100), 1) if total_days > 0 else 0

        return {
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "total_days": total_days,
            "total_commits": total_commits,
            "total_active_days": total_active_days,
            "activity_percentage": activity_percentage,
            "max_streak": max_streak,
            "busiest_day": busiest_day,
            "year_stats": year_stats,
            "calendar": calendar
        }

    def generate_commits(
        self,
        simulation_data: Dict[str, Any],
        author_name: Optional[str] = None,
        author_email: Optional[str] = None,
        branch: str = "main",
        clean_slate: bool = False,
        bypass_hooks: bool = True,
        activity_file: str = "activity.txt",
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """
        Executes backdated Git commits for each active day in simulation_data.
        Safely bypasses local hooks with --no-verify.
        Optionally resets the branch with an automatic backup tag.
        """
        git_info = self.get_git_info()
        name = author_name or git_info.get("user_name") or "Developer"
        email = author_email or git_info.get("user_email") or "developer@example.com"

        # Disable background auto-gc during batch operations
        self.run_git(["config", "gc.auto", "0"])

        # Backup creation if clean_slate
        backup_tag = None
        if clean_slate and git_info.get("commit_count", 0) > 0:
            backup_tag = f"backup-pre-green-{int(time.time())}"
            self.run_git(["tag", backup_tag])

        # If clean_slate, safely reset to an orphan branch or initial commit
        if clean_slate:
            # Create a clean orphan branch to start the graph cleanly from scratch
            temp_branch = f"green-temp-{int(time.time())}"
            self.run_git(["checkout", "--orphan", temp_branch])
            
            # Ensure activity file exists and is tracked
            act_path = os.path.join(self.repo_path, activity_file)
            with open(act_path, "w") as f:
                f.write(f"# Historical GitHub Contribution Graph (2019-2026)\n# Author: {name} <{email}>\n")
            
            # Stage all project files so the tools, UI, and docs are preserved in history
            self.run_git(["add", "."])

            # Initial backdated commit
            init_date = f"{simulation_data['start_date']} 09:00:00 +0500"
            env = {
                "GIT_AUTHOR_NAME": name,
                "GIT_AUTHOR_EMAIL": email,
                "GIT_AUTHOR_DATE": init_date,
                "GIT_COMMITTER_NAME": name,
                "GIT_COMMITTER_EMAIL": email,
                "GIT_COMMITTER_DATE": init_date,
            }
            commit_cmd = ["commit", "-m", "chore: initialize project history and repository files"]
            if bypass_hooks:
                commit_cmd.insert(1, "--no-verify")
            self.run_git(commit_cmd, env=env)

            # Move branch to target branch
            self.run_git(["branch", "-M", branch])
        else:
            # Ensure branch exists and is checked out
            self.run_git(["checkout", branch])
            act_path = os.path.join(self.repo_path, activity_file)
            if not os.path.exists(act_path):
                with open(act_path, "w") as f:
                    f.write(f"# Historical GitHub Contribution Graph (2019-2026)\n# Author: {name} <{email}>\n")
                self.run_git(["add", activity_file])
                self.run_git(["commit", "-m", "chore: add activity tracking file", "--no-verify"])

        total_calendar_days = len(simulation_data["calendar"])
        active_days = [d for d in simulation_data["calendar"] if d["commits"] > 0]
        total_commits_to_make = simulation_data["total_commits"]

        commits_made = 0
        days_processed = 0
        start_time = time.time()
        act_path = os.path.join(self.repo_path, activity_file)

        msg_count = len(COMMIT_MESSAGES)
        rng = random.Random(1337)

        for day in active_days:
            date_str = day["date"]
            count = day["commits"]

            for c_idx in range(count):
                # Spread commits realistically between 09:15 and 22:30
                hour = 9 + int((13.0 * c_idx) / max(1, count)) + rng.randint(0, 1)
                minute = rng.randint(0, 59)
                second = rng.randint(0, 59)
                timestamp = f"{date_str} {hour:02d}:{minute:02d}:{second:02d} +0500"

                # Pick a diverse realistic commit message
                msg_base = COMMIT_MESSAGES[(commits_made + c_idx) % msg_count]
                commit_msg = f"{msg_base} [{date_str} #{c_idx+1}]"

                # Append to activity file
                with open(act_path, "a") as f:
                    f.write(f"Commit {commits_made + 1} | {timestamp} | {commit_msg}\n")

                # Commit specifically the activity file
                commit_env = {
                    "GIT_AUTHOR_NAME": name,
                    "GIT_AUTHOR_EMAIL": email,
                    "GIT_AUTHOR_DATE": timestamp,
                    "GIT_COMMITTER_NAME": name,
                    "GIT_COMMITTER_EMAIL": email,
                    "GIT_COMMITTER_DATE": timestamp,
                }
                cmd = ["commit", "-m", commit_msg]
                if bypass_hooks:
                    cmd.insert(1, "--no-verify")
                cmd.append(activity_file)

                ret, out, err = self.run_git(cmd, env=commit_env)
                if ret != 0:
                    raise RuntimeError(f"Git commit failed on {timestamp}: {err or out}")

                commits_made += 1

            days_processed += 1
            if progress_callback:
                elapsed = time.time() - start_time
                pct = round((commits_made / total_commits_to_make) * 100, 1) if total_commits_to_make else 100
                progress_callback({
                    "commits_made": commits_made,
                    "total_commits": total_commits_to_make,
                    "days_processed": days_processed,
                    "total_active_days": len(active_days),
                    "current_date": date_str,
                    "percentage": pct,
                    "elapsed_sec": round(elapsed, 1),
                    "is_complete": False
                })

        total_elapsed = round(time.time() - start_time, 2)
        final_info = self.get_git_info()

        result = {
            "success": True,
            "commits_generated": commits_made,
            "total_commits_now": final_info.get("commit_count", 0),
            "elapsed_seconds": total_elapsed,
            "branch": branch,
            "author_name": name,
            "author_email": email,
            "backup_tag": backup_tag,
            "activity_file": activity_file
        }

        if progress_callback:
            progress_callback({
                "commits_made": commits_made,
                "total_commits": total_commits_to_make,
                "days_processed": days_processed,
                "total_active_days": len(active_days),
                "current_date": simulation_data["end_date"],
                "percentage": 100.0,
                "elapsed_sec": total_elapsed,
                "is_complete": True,
                "result": result
            })

        return result

    def push_to_remote(
        self,
        remote: str = "origin",
        branch: str = "main",
        force: bool = True,
        bypass_hooks: bool = True
    ) -> Dict[str, Any]:
        """Safely pushes the committed graph to the target remote."""
        cmd = ["push"]
        if force:
            cmd.append("--force")
        if bypass_hooks:
            cmd.append("--no-verify")
        cmd.extend([remote, branch])

        ret, out, err = self.run_git(cmd)
        return {
            "success": ret == 0,
            "exit_code": ret,
            "stdout": out,
            "stderr": err,
            "command": "git " + " ".join(cmd)
        }
