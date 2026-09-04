import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime

# Add root directory to sys.path
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
from rich import box

from nyx.mcp_server.db import DEFAULT_DB_PATH
from nyx.mcp_server.state_mem import StateMemEngine

console = Console()

def create_header() -> Panel:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = Text(" Nyx Hybrid Memory System • Mission Control Monitor", style="bold cyan")
    subtitle = Text(f"Status: ONLINE  │  Engine: StateMem G=(U,E)  │  DB: Active  │  Time: {now}", style="dim")
    content = Text.assemble(title, "\n", subtitle)
    return Panel(content, box=box.ROUNDED, border_style="cyan")

def create_state_table(db_path: Path) -> Panel:
    table = Table(box=box.SIMPLE_HEAVY, expand=True, header_style="bold magenta")
    table.add_column("State Unit ID", style="bold white", width=22)
    table.add_column("Content / Value", style="white", ratio=2)
    table.add_column("Status", width=18, justify="center")
    table.add_column("Dependencies", style="dim cyan", ratio=1)
    table.add_column("Source", style="dim", ratio=1)

    try:
        sm = StateMemEngine(db_path)
        states = sm.get_state(include_all=True)
        if not states:
            table.add_row("(No state units recorded yet)", "-", "-", "-", "-")
        else:
            for uid, val in sorted(states.items(), key=lambda x: (x[1]["priority"], x[0])):
                status = val["status"]
                if status == "active":
                    status_badge = Text("● ACTIVE", style="bold green")
                elif status == "needs_recheck":
                    status_badge = Text("▲ NEEDS_RECHECK", style="bold red on yellow")
                else:
                    status_badge = Text("○ SUPERSEDED", style="dim")

                content_val = val["content"]
                content_str = json.dumps(content_val, ensure_ascii=False) if isinstance(content_val, (dict, list)) else str(content_val)
                deps_str = ", ".join(val["deps"]) if val["deps"] else "(none)"
                source_str = str(val["source"])

                table.add_row(uid, content_str[:60], status_badge, deps_str, source_str[:30])
    except Exception as e:
        table.add_row("Error loading states", str(e), "-", "-", "-")

    return Panel(table, title="[bold yellow]1. Active StateMem Graph G=(U,E) Snapshot[/bold yellow]", border_style="yellow")

def create_activity_table() -> Panel:
    table = Table(box=box.SIMPLE_HEAVY, expand=True, header_style="bold cyan")
    table.add_column("Time", width=10, style="dim")
    table.add_column("Status", width=8, justify="center")
    table.add_column("Tool Name", style="bold yellow", width=20)
    table.add_column("Execution Summary & State Transitions", style="white", ratio=3)

    log_file = root_dir / "nyx" / "logs" / "activity.jsonl"
    if not log_file.exists():
        table.add_row("-", "-", "(No tool activity logged yet)", "Agent has not called tools yet.")
    else:
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
            
            recent_lines = lines[-8:]
            for line in reversed(recent_lines):
                entry = json.loads(line)
                t_str = entry.get("local_time", "")[-8:]
                is_err = entry.get("is_error", False)
                status_badge = Text("[ERR]", style="bold red") if is_err else Text("[OK]", style="bold green")
                tool_name = entry.get("tool", "")
                summary = entry.get("summary", "")

                table.add_row(t_str, status_badge, tool_name, summary)
        except Exception as e:
            table.add_row("-", "-", "Log parse error", str(e))

    return Panel(table, title="[bold green]2. Real-Time Agent Tool Activity Stream[/bold green]", border_style="green")

def make_dashboard() -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(create_header(), size=4),
        Layout(name="state_section", ratio=1),
        Layout(name="activity_section", ratio=1),
        Layout(Panel(Text("Press Ctrl+C to exit monitor. Watching Agent activity in real-time...", style="italic dim center"), box=box.MINIMAL), size=3)
    )
    layout["state_section"].update(create_state_table(DEFAULT_DB_PATH))
    layout["activity_section"].update(create_activity_table())
    return layout

def main():
    console.clear()
    console.print("[bold green]Starting Nyx Real-Time Mission Control Monitor...[/bold green]")
    time.sleep(0.5)

    with Live(make_dashboard(), refresh_per_second=2, screen=True) as live:
        try:
            while True:
                live.update(make_dashboard())
                time.sleep(1.0)
        except KeyboardInterrupt:
            pass

    console.print("[yellow]Nyx Monitor stopped.[/yellow]")

if __name__ == "__main__":
    main()
