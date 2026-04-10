import os
import frappe
from frappe.utils import get_bench_path

# Define log file paths relative to this module or bench
# Kafka Logs: apps/rndopsapp/rndopsapp/rndopsapp/kafka/logs/files/
KAFKA_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs', 'files')
BENCH_LOG_DIR = os.path.join(get_bench_path(), 'logs')

# Map log types to their absolute paths
LOG_FILES = {
    'consumer': os.path.join(KAFKA_LOG_DIR, 'consumer.log'),
    'producer': os.path.join(KAFKA_LOG_DIR, 'producer.log'),
    'error': os.path.join(KAFKA_LOG_DIR, 'error.log'),
    'debug': os.path.join(KAFKA_LOG_DIR, 'debug.log'),
    'frappe': os.path.join(BENCH_LOG_DIR, 'frappe.log'),
    'worker': os.path.join(BENCH_LOG_DIR, 'worker.log'),
    'scheduler': os.path.join(BENCH_LOG_DIR, 'scheduler.log'),
    'web': os.path.join(BENCH_LOG_DIR, 'web.log'),
    'terminal': os.path.join(BENCH_LOG_DIR, 'terminal.log') # For manual redirect: bench start | tee logs/terminal.log
}

import subprocess

def get_kafka_logs(log_type='consumer', lines=100, search_string=None):
    """
    Reads the last N lines from the specified log file or tmux session.
    Optionally filters lines containing search_string.
    """
    if log_type not in LOG_FILES:
        return {"error": "Invalid log type"}

    try:
        content = []
        if log_type == 'terminal':
            # Capture the last N lines from the 'frappe' tmux session
            # -p: print to stdout
            # -t: target pane
            # -S: start line (negative for history)
            # Note: For search effectiveness in terminal, we might want to capture MORE lines if search is active,
            # but for now we stick to the requested N lines window.
            result = subprocess.run(
                ['tmux', 'capture-pane', '-pt', 'frappe', '-S', f'-{lines}'],
                capture_output=True,
                text=True,
                check=True
            )
            content = result.stdout.splitlines()
        else:
            file_path = LOG_FILES[log_type]
            if not os.path.exists(file_path):
                # Check for legacy path logic or simply return error
                if hasattr(KAFKA_LOG_DIR, 'startswith') and file_path.startswith(KAFKA_LOG_DIR):
                     if not os.path.exists(KAFKA_LOG_DIR):
                        os.makedirs(KAFKA_LOG_DIR, exist_ok=True)
                return {"content": [f"Log file not found: {os.path.basename(file_path)}"]}

            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                # Efficiently reading last N lines is tricky with variable line lengths.
                # Reading all lines is okay for typical log sizes in this context (e.g. < 10MB).
                # Ideally use `deque(f, lines)` but standard readlines is fine here.
                all_lines = f.readlines()
                content = [line.rstrip() for line in all_lines[-int(lines):]]

        # Filter if search_string provided
        if search_string:
            content = [line for line in content if search_string.lower() in line.lower()]

        return {"content": content}

    except subprocess.CalledProcessError as e:
        return {"error": f"Failed to capture tmux pane: {e.stderr or str(e)}"}
    except Exception as e:
        return {"error": f"Failed to read logs: {str(e)}"}
