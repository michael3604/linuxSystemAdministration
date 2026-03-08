#!/usr/bin/env python3
# For detailed instructions please run --help or see the parse_arguments function below

import subprocess
import argparse
from datetime import datetime
import re
import time

def parse_arguments():
    """Parses command-line arguments and returns them."""
    parser = argparse.ArgumentParser(
        description=(
            "Folder Change Watcher\n"
            "Watches specified ZFS filesystems for changes and triggers a script.\n"
            "This script retrieves the list of watched filesystems from the output of "
            "auditctl -l and executes the snapshot creation script when changes are detected."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    
    parser.add_argument(
        "--audit-log-key-template",
        type=str,
        default="file-change-watcher-{}",
        help="Template for the audit log key used to filter changes."
    )
    
    parser.add_argument(
        "--check-interval",
        type=int,
        default=30,
        help="Time (in seconds) to wait between checks for changes."
    )
    
    return parser.parse_args()

def get_watched_filesystems(audit_log_key_template):
    """Retrieves the list of watched filesystems from the output of auditctl -l."""
    try:
        # Execute auditctl -l and capture the output
        result = subprocess.run(
            ["auditctl", "-l"],
            stdout=subprocess.PIPE,
            text=True,
            check=True
        )
        
        lines = result.stdout.splitlines()
        
        # Filter lines based on the audit log key template
        filesystems = []
        for line in lines:
            if audit_log_key_template.format('') in line:  # Check if the template is in the line
                match = re.search(r"-w\s+(/[^ ]+)", line)  # Matches -w followed by the path
                if match:
                    filesystems.append(match.group(1))
        
        return filesystems
    except subprocess.CalledProcessError as e:
        print(f"Error retrieving watched filesystems: {e}")
        return []

def check_audit_logs(audit_key):
    """Checks the audit logs for changes associated with the specified audit key, returning the first match."""
    try:
        # Use a subprocess to read the output line by line
        process = subprocess.Popen(
            ["ausearch", "-k", audit_key, "-ts", "recent"],
            stdout=subprocess.PIPE,
            text=True
        )

        for line in process.stdout:
            if line.strip():  # Only process non-empty lines
                return line.strip()  # Return the first non-empty line as the output

        return ""  # Return an empty string if no matches are found

    except subprocess.CalledProcessError as e:
        print(f"Error checking audit logs: {e}")
        return ""

def execute_snapshot_script(filesystem):
    """Executes the snapshot creation script."""
    subprocess.run(["python3", "/scripts/snapshot-create.py", "--filesystem", filesystem])

def main():
    # Parse command-line arguments
    args = parse_arguments()

    # Get the list of watched filesystems from auditctl
    filesystems = get_watched_filesystems(args.audit_log_key_template)

    if not filesystems:
        print("No watched filesystems found. Exiting.")
        return

    print(f"Watching the following filesystems: {', '.join(filesystems)}")

    try:
        while True:
            # Track which filesystems have already had snapshots created
            processed_filesystems = set()

            for fs in filesystems:
                audit_key = args.audit_log_key_template.format(fs)  # Use the provided audit log key template
                log_output = check_audit_logs(audit_key)  # Check for the first match only

                if log_output and fs not in processed_filesystems:
                    print(f"[{datetime.now()}] Changes detected in {fs}:")
                    print(log_output)
                    execute_snapshot_script(fs)
                    processed_filesystems.add(fs)  # Mark this filesystem as processed

            time.sleep(args.check_interval)  # Use the specified check interval
    
    except KeyboardInterrupt:
        print("Stopping folder watcher.")

if __name__ == "__main__":
    main()
