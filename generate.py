#!/usr/bin/env python3
"""
generate.py - Command Line Interface for GitHub Contribution Graph Customizer.

Automates and customizes historical GitHub contribution graphs from 2019 to 2026.
Supports custom yearly density curves, randomized daily distributions,
backdated commits with custom author/committer dates, hook bypassing,
and safe force pushing.
"""

import os
import sys
import argparse
import json
import webbrowser
from datetime import datetime, date
from engine import ContributionEngine, PRESET_CONFIGS


def print_banner():
    banner = """
\033[1;32m╔══════════════════════════════════════════════════════════════════════════════╗
║                  GITHUB CONTRIBUTION GRAPH PAINTER & AUTOMATOR               ║
║                        Historical Years: 2019 → 2026                         ║
╚══════════════════════════════════════════════════════════════════════════════╝\033[0m
"""
    print(banner)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Automate and customize historical GitHub contribution graphs (2019 - 2026)."
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Launch the interactive Web UI and dashboard in your browser."
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for Web UI (default: 8080)."
    )
    parser.add_argument(
        "--preset",
        choices=list(PRESET_CONFIGS.keys()),
        default="progressive",
        help="Contribution curve preset (default: progressive)."
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=2019,
        help="Starting year (default: 2019)."
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=2026,
        help="Ending year (default: 2026)."
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default="2026-10-12",
        help="Specific end date in YYYY-MM-DD format (default: present date 2026-10-12)."
    )
    parser.add_argument(
        "--weekend-weight",
        type=float,
        default=0.35,
        help="Activity multiplier on weekends (0.0 = no weekend commits, 1.0 = equal to weekdays)."
    )
    parser.add_argument(
        "--author-name",
        type=str,
        default=None,
        help="Git author name (defaults to git config user.name)."
    )
    parser.add_argument(
        "--author-email",
        type=str,
        default=None,
        help="Git author email (must match your GitHub account email!)."
    )
    parser.add_argument(
        "--branch",
        type=str,
        default="main",
        help="Target Git branch (default: main)."
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean slate: resets branch history from start year with an automatic backup tag."
    )
    parser.add_argument(
        "--no-bypass-hooks",
        action="store_true",
        help="Do not bypass local Git hooks (hooks are bypassed with --no-verify by default)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate and print calendar statistics without creating any commits."
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Force push the generated commits to the target remote after creation."
    )
    parser.add_argument(
        "--remote",
        type=str,
        default="origin",
        help="Remote name for pushing (default: origin)."
    )
    parser.add_argument(
        "--config-file",
        type=str,
        default=None,
        help="Path to custom JSON configuration file."
    )
    return parser.parse_args()


def run_cli():
    print_banner()
    args = parse_args()

    if args.web:
        print("\033[1;36m[i] Launching interactive Web UI...\033[0m")
        from app import start_server
        start_server(port=args.port, open_browser=True)
        return

    engine = ContributionEngine(".")
    git_info = engine.get_git_info()

    if not git_info.get("is_git_repo"):
        print("\033[1;31m[!] Error: Current directory is not a Git repository.\033[0m")
        sys.exit(1)

    print(f"\033[1;34m[+] Git Repository Info:\033[0m")
    print(f"    Branch:        {git_info.get('branch')}")
    print(f"    Remote:        {git_info.get('remote_url') or 'None'}")
    print(f"    Author Name:   {args.author_name or git_info.get('user_name')}")
    print(f"    Author Email:  {args.author_email or git_info.get('user_email')} \033[1;33m(Must match your GitHub account!)\033[0m")
    print(f"    Current Commits: {git_info.get('commit_count')}")
    print(f"    Active Hooks:  {len(git_info.get('active_hooks', []))} (Hooks will be bypassed with --no-verify)")
    print()

    # Load year configuration
    if args.config_file and os.path.exists(args.config_file):
        with open(args.config_file, "r") as f:
            custom_cfg = json.load(f)
            year_configs = {int(k): v for k, v in custom_cfg.get("years", {}).items()}
            weekend_weight = custom_cfg.get("weekend_weight", args.weekend_weight)
    else:
        preset_data = PRESET_CONFIGS.get(args.preset, PRESET_CONFIGS["progressive"])
        year_configs = preset_data["years"]
        weekend_weight = args.weekend_weight or preset_data.get("weekend_weight", 0.35)

    # Date ranges
    start_date = date(args.start_year, 1, 1)
    end_parts = [int(p) for p in args.end_date.split("-")]
    end_date = date(end_parts[0], end_parts[1], end_parts[2])

    print(f"\033[1;34m[+] Simulation Configuration:\033[0m")
    print(f"    Preset:         {args.preset.upper()}")
    print(f"    Range:          {start_date} to {end_date} ({(end_date - start_date).days + 1} days)")
    print(f"    Weekend Weight: {weekend_weight}x")
    print(f"    History Mode:   {'Clean Slate (Reset with backup)' if args.clean else 'Append to current history'}")
    print()

    sim = engine.simulate(
        year_configs=year_configs,
        start_date=start_date,
        end_date=end_date,
        weekend_weight=weekend_weight
    )

    print("\033[1;32m[+] Projected Yearly Contribution Breakdown:\033[0m")
    print("┌──────┬───────────────┬──────────────────────────┬─────────────────┐")
    print("│ Year │ Total Commits │ Active Days / Total Days │ Activity Rate   │")
    print("├──────┼───────────────┼──────────────────────────┼─────────────────┤")
    for y, s in sorted(sim["year_stats"].items()):
        act_pct = round(s["active_days"] / s["total_days"] * 100, 1) if s["total_days"] else 0
        print(f"│ {y:<4} │ {s['total_commits']:<13} │ {s['active_days']:<4} / {s['total_days']:<17} │ {act_pct:<6}%         │")
    print("└──────┴───────────────┴──────────────────────────┴─────────────────┘")
    print(f"  \033[1;32mTotal Projected Commits:\033[0m {sim['total_commits']}")
    print(f"  \033[1;32mTotal Active Days:\033[0m       {sim['total_active_days']} ({sim['activity_percentage']}%)")
    print(f"  \033[1;32mLongest Streak:\033[0m          {sim['max_streak']} consecutive days")
    print(f"  \033[1;32mBusiest Day:\033[0m             {sim['busiest_day']['date']} ({sim['busiest_day']['commits']} commits)")
    print()

    if args.dry_run:
        print("\033[1;33m[!] Dry run mode specified. No Git commits were created.\033[0m")
        print("\033[1;36m[i] Tip: Run without --dry-run to write commits, or run with --web for the visual UI.\033[0m")
        return

    # Confirmation prompt if run interactively in terminal
    if sys.stdin.isatty():
        resp = input(f"\033[1;33m[?] Ready to generate {sim['total_commits']} commits into branch '{args.branch}'? (y/N): \033[0m")
        if resp.lower() not in ("y", "yes"):
            print("Aborted.")
            return

    def cli_progress(update):
        pct = update.get("percentage", 0)
        curr_d = update.get("current_date", "")
        made = update.get("commits_made", 0)
        total = update.get("total_commits", 0)
        elapsed = update.get("elapsed_sec", 0)
        bar_len = 30
        filled = int(bar_len * pct / 100)
        bar = "█" * filled + "░" * (bar_len - filled)
        sys.stdout.write(f"\r\033[K\033[1;32m[{bar}] {pct:5.1f}%\033[0m | Date: {curr_d} | Commits: {made}/{total} | {elapsed}s")
        sys.stdout.flush()

    print("\033[1;34m[+] Executing backdated commits...\033[0m")
    res = engine.generate_commits(
        simulation_data=sim,
        author_name=args.author_name,
        author_email=args.author_email,
        branch=args.branch,
        clean_slate=args.clean,
        bypass_hooks=not args.no_bypass_hooks,
        progress_callback=cli_progress
    )
    print("\n")
    print(f"\033[1;32m[✓] Successfully generated {res['commits_generated']} commits in {res['elapsed_seconds']} seconds!\033[0m")
    if res.get("backup_tag"):
        print(f"    Safety backup created at tag: \033[1;33m{res['backup_tag']}\033[0m")
    print(f"    Current total repository commits: \033[1;32m{res['total_commits_now']}\033[0m")

    # Force push if requested
    if args.push:
        print(f"\n\033[1;33m[?] Push requested to remote '{args.remote}' on branch '{args.branch}'...\033[0m")
        if sys.stdin.isatty():
            confirm = input(f"Confirm force push to {git_info.get('remote_url')}? (y/N): ")
            if confirm.lower() not in ("y", "yes"):
                print("Push aborted.")
                return

        print("\033[1;34m[+] Pushing commits to remote...\033[0m")
        push_res = engine.push_to_remote(
            remote=args.remote,
            branch=args.branch,
            force=True,
            bypass_hooks=not args.no_bypass_hooks
        )
        if push_res["success"]:
            print("\033[1;32m[✓] Successfully pushed to remote! GitHub will update your contribution graph shortly.\033[0m")
        else:
            print(f"\033[1;31m[!] Push failed:\033[0m {push_res.get('stderr') or push_res.get('stdout')}")
    else:
        print(f"\n\033[1;36m[i] Next step: When ready, push to GitHub using:\033[0m")
        print(f"    git push --force origin {args.branch}")


if __name__ == "__main__":
    run_cli()
