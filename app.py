#!/usr/bin/env python3
"""
app.py - Lightweight Local Web Server & API for GitHub Contribution Automator.

Provides:
- Web dashboard on http://localhost:8080 (or next open port)
- REST API for git status, simulation, commit generation, and remote push
- Thread-safe background execution with real-time progress polling
- Zero external dependencies (uses standard library http.server)
"""

import os
import sys
import json
import time
import socket
import threading
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, date

from engine import ContributionEngine, PRESET_CONFIGS


# Global Execution Job State
JOB_STATE = {
    "status": "idle",       # "idle", "running", "completed", "error"
    "progress": 0.0,
    "current_date": "",
    "commits_made": 0,
    "total_commits": 0,
    "days_processed": 0,
    "total_active_days": 0,
    "elapsed_sec": 0,
    "logs": [],
    "result": None,
    "error": None
}
JOB_LOCK = threading.Lock()


def add_log(msg: str):
    with JOB_LOCK:
        timestamp = datetime.now().strftime("%H:%M:%S")
        JOB_STATE["logs"].append(f"[{timestamp}] {msg}")
        # Keep last 500 logs
        if len(JOB_STATE["logs"]) > 500:
            JOB_STATE["logs"].pop(0)


class GreenHandler(SimpleHTTPRequestHandler):
    """Custom HTTP handler serving static UI and REST API."""

    def __init__(self, *args, **kwargs):
        web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
        super().__init__(*args, directory=web_dir, **kwargs)

    def log_message(self, format, *args):
        # Silence routine static asset HTTP logs to keep console clean
        return

    def send_json(self, status_code: int, data: dict):
        response = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(response)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/status":
            engine = ContributionEngine(".")
            info = engine.get_git_info()
            self.send_json(200, info)
            return

        elif path == "/api/presets":
            self.send_json(200, PRESET_CONFIGS)
            return

        elif path == "/api/progress":
            with JOB_LOCK:
                copy_state = dict(JOB_STATE)
            self.send_json(200, copy_state)
            return

        # Serve static assets from web/
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self.send_json(400, {"error": "Invalid JSON"})
            return

        engine = ContributionEngine(".")

        if path == "/api/simulate":
            try:
                preset = payload.get("preset", "progressive")
                weekend_weight = float(payload.get("weekend_weight", 0.35))
                start_year = int(payload.get("start_year", 2019))
                end_date_str = payload.get("end_date", "2026-10-12")

                start_date = date(start_year, 1, 1)
                end_parts = [int(p) for p in end_date_str.split("-")]
                end_date = date(end_parts[0], end_parts[1], end_parts[2])

                # Year configs
                if "years" in payload and payload["years"]:
                    year_configs = {int(k): v for k, v in payload["years"].items()}
                else:
                    year_configs = PRESET_CONFIGS.get(preset, PRESET_CONFIGS["progressive"])["years"]

                sim = engine.simulate(
                    year_configs=year_configs,
                    start_date=start_date,
                    end_date=end_date,
                    weekend_weight=weekend_weight
                )
                self.send_json(200, sim)
            except Exception as e:
                self.send_json(500, {"error": str(e)})
            return

        elif path == "/api/author":
            try:
                name = payload.get("name")
                email = payload.get("email")
                if not name or not email:
                    self.send_json(400, {"error": "name and email required"})
                    return
                ok = engine.set_author(name, email)
                self.send_json(200, {"success": ok, "name": name, "email": email})
            except Exception as e:
                self.send_json(500, {"error": str(e)})
            return

        elif path == "/api/generate":
            global JOB_STATE
            with JOB_LOCK:
                if JOB_STATE["status"] == "running":
                    self.send_json(409, {"error": "A commit generation job is already in progress"})
                    return
                JOB_STATE["status"] = "running"
                JOB_STATE["progress"] = 0.0
                JOB_STATE["logs"] = []
                JOB_STATE["result"] = None
                JOB_STATE["error"] = None
                JOB_STATE["commits_made"] = 0
                JOB_STATE["total_commits"] = 0

            # Run in worker thread
            def worker():
                try:
                    add_log("Starting commit generation process...")
                    clean_slate = payload.get("clean_slate", False)
                    bypass_hooks = payload.get("bypass_hooks", True)
                    author_name = payload.get("author_name")
                    author_email = payload.get("author_email")
                    branch = payload.get("branch", "main")
                    sim_data = payload.get("simulation")

                    if not sim_data:
                        # Generate simulation on the fly
                        preset = payload.get("preset", "progressive")
                        weekend_weight = float(payload.get("weekend_weight", 0.35))
                        start_year = int(payload.get("start_year", 2019))
                        end_date_str = payload.get("end_date", "2026-10-12")
                        start_date = date(start_year, 1, 1)
                        end_parts = [int(p) for p in end_date_str.split("-")]
                        end_date = date(end_parts[0], end_parts[1], end_parts[2])

                        if "years" in payload and payload["years"]:
                            year_configs = {int(k): v for k, v in payload["years"].items()}
                        else:
                            year_configs = PRESET_CONFIGS.get(preset, PRESET_CONFIGS["progressive"])["years"]

                        sim_data = engine.simulate(
                            year_configs=year_configs,
                            start_date=start_date,
                            end_date=end_date,
                            weekend_weight=weekend_weight
                        )

                    add_log(f"Plan: {sim_data['total_commits']} commits across {sim_data['total_active_days']} active days.")
                    if clean_slate:
                        add_log("Clean slate mode: Creating safety backup tag and initializing fresh branch.")
                    else:
                        add_log(f"Append mode: Preserving existing history on '{branch}'.")

                    def on_progress(p):
                        with JOB_LOCK:
                            JOB_STATE["progress"] = p.get("percentage", 0)
                            JOB_STATE["current_date"] = p.get("current_date", "")
                            JOB_STATE["commits_made"] = p.get("commits_made", 0)
                            JOB_STATE["total_commits"] = p.get("total_commits", 0)
                            JOB_STATE["days_processed"] = p.get("days_processed", 0)
                            JOB_STATE["total_active_days"] = p.get("total_active_days", 0)
                            JOB_STATE["elapsed_sec"] = p.get("elapsed_sec", 0)
                        if p.get("commits_made", 0) % 250 == 0 or p.get("is_complete"):
                            add_log(f"Processed: {p.get('commits_made')}/{p.get('total_commits')} commits ({p.get('percentage')}%) - Date: {p.get('current_date')}")

                    result = engine.generate_commits(
                        simulation_data=sim_data,
                        author_name=author_name,
                        author_email=author_email,
                        branch=branch,
                        clean_slate=clean_slate,
                        bypass_hooks=bypass_hooks,
                        progress_callback=on_progress
                    )

                    with JOB_LOCK:
                        JOB_STATE["status"] = "completed"
                        JOB_STATE["result"] = result
                        JOB_STATE["progress"] = 100.0

                    add_log(f"Success! {result['commits_generated']} commits generated in {result['elapsed_seconds']}s.")
                    if result.get("backup_tag"):
                        add_log(f"Backup tag created: {result['backup_tag']}")
                except Exception as ex:
                    with JOB_LOCK:
                        JOB_STATE["status"] = "error"
                        JOB_STATE["error"] = str(ex)
                    add_log(f"Error encountered: {str(ex)}")

            t = threading.Thread(target=worker, daemon=True)
            t.start()

            self.send_json(202, {"message": "Generation started", "status": "running"})
            return

        elif path == "/api/push":
            try:
                remote = payload.get("remote", "origin")
                branch = payload.get("branch", "main")
                force = payload.get("force", True)
                bypass_hooks = payload.get("bypass_hooks", True)

                add_log(f"Executing push to remote '{remote}', branch '{branch}' (force={force})...")
                res = engine.push_to_remote(
                    remote=remote,
                    branch=branch,
                    force=force,
                    bypass_hooks=bypass_hooks
                )
                if res["success"]:
                    add_log("Push completed successfully!")
                else:
                    add_log(f"Push failed: {res.get('stderr') or res.get('stdout')}")

                self.send_json(200, res)
            except Exception as e:
                self.send_json(500, {"error": str(e)})
            return

        self.send_json(404, {"error": "Not found"})


def find_available_port(start_port: int = 8080) -> int:
    port = start_port
    while port < start_port + 100:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
        port += 1
    return start_port


def start_server(port: int = 8080, open_browser: bool = False):
    actual_port = find_available_port(port)
    server_address = ("127.0.0.1", actual_port)
    httpd = HTTPServer(server_address, GreenHandler)

    url = f"http://localhost:{actual_port}"
    print(f"\n\033[1;32m══════════════════════════════════════════════════════════════════════════\033[0m")
    print(f"\033[1;32m   GitHub Contribution Automator Web UI running at:\033[0m")
    print(f"\033[1;36m   👉  {url}\033[0m")
    print(f"\033[1;32m══════════════════════════════════════════════════════════════════════════\033[0m\n")

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        httpd.server_close()


if __name__ == "__main__":
    start_server(open_browser=False)
