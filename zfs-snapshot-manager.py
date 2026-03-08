#!/usr/bin/env python3
'''
Licence:
Copyright 2024 Michael Neumeier
Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.

For technical documentation please see function "parse_arguments" a bit further down.
'''

import argparse
import os
import subprocess
from datetime import datetime, timedelta, timezone

# Function to set up and handle command-line arguments using argparse
def parse_arguments():
    class CustomFormatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawTextHelpFormatter):
        pass

    parser = argparse.ArgumentParser(formatter_class=CustomFormatter)
    parser.description = "creates and prunes zfs snapshots with ISO timestamp."
    parser.epilog = (
        "Example usage:\n"
        f"  sudo {parser.prog} \n"
        f"  sudo {parser.prog} -p tank -d 12 -m=40 -n 10\n"
    )

    parser.add_argument('-p', '--pool', default="tank", help='zfs pool. e.g. "tank" or "data"')
    parser.add_argument('-d', '--days', default=14, type=int, help='number of days a snapshot is kept')
    parser.add_argument('-w', '--weeks', default=8, type=int, help='number of weeks for which one snapshot each is kept')
    parser.add_argument('-m', '--months', default=36, type=int, help='number of months for which one snapshot each is kept')
    parser.add_argument('-n', '--newest', default=50, type=int, help='always keep the newest N snapshots regardless of age')
    parser.add_argument('-v', '--verbose', action='store_true', help='enable verbose output')
    parser.add_argument('--dry-run', action='store_true', help='enable dry-run mode where no scripts are executed.')

    return parser.parse_args()

# (dry-)run commands
def run_cmd(command):
    command_str = ' '.join(command) if isinstance(command, list) else command  # turn into string if necessary
    if args.dry_run:
        verboseprint(f"D R Y   R U N! not executing {command_str}")
    else:
        verboseprint(f"Executing {command_str}")
        subprocess.run({command_str}, shell=True, check=True, executable="/bin/bash")

def parse_snapshot_name(snapshot_name):
    try:
        return datetime.strptime(snapshot_name.replace("backup_", ""), "%Y-%m-%dT%H:%M:%S%Z")
    except ValueError:
        return None

def filter_snapshots(snapshots):
    snapshots.sort()  # Sort by date (oldest first)
    keepers = []

    now = datetime.now()

    # Always keep the newest N snapshots
    newest_to_keep = snapshots[-args.newest:] if args.newest > 0 else []
    keepers.extend(newest_to_keep)

    for snapshot in snapshots:
        if snapshot in keepers:
            continue  # Already marked to keep

        snapshot_date = parse_snapshot_name(snapshot)
        if not snapshot_date:
            verboseprint(snapshot, "cannot be processed and will therefore be kept.")
            keepers.append(snapshot)
            continue

        # Daily retention
        if snapshot_date >= now - timedelta(days=args.days):
            verboseprint(snapshot, "will be kept (daily retention)")
            keepers.append(snapshot)
            continue

        # Weekly retention
        if snapshot_date >= now - timedelta(weeks=args.weeks):
            if all(abs((snapshot_date - parse_snapshot_name(kept)).days) >= 7 for kept in keepers if parse_snapshot_name(kept)):
                verboseprint(snapshot, "will be kept (weekly retention)")
                keepers.append(snapshot)
                continue

        # Monthly retention
        if snapshot_date >= now - timedelta(weeks=args.months * 4):
            if all(snapshot_date.month != parse_snapshot_name(kept).month or snapshot_date.year != parse_snapshot_name(kept).year
                   for kept in keepers if parse_snapshot_name(kept)):
                verboseprint(snapshot, "will be kept (monthly retention)")
                keepers.append(snapshot)
                continue

        verboseprint(snapshot, "will be removed")
    return keepers

def delete_snapshots(pool, snapshots_to_delete):
    for snapshot in snapshots_to_delete:
        snapshot_path = f"{pool}@{snapshot}"
        try:
            print(f"Deleting snapshot: {snapshot_path}")
            run_cmd(["zfs", "destroy", snapshot_path])
        except subprocess.CalledProcessError as e:
            print(f"Failed to delete snapshot {snapshot_path}: {e}")

def main():
    try:
        verboseprint("Creating ZFS snapshots")
        result = subprocess.run(["zfs", "list", "-H", "-o", "name"], capture_output=True, text=True, check=True)
        filesystems = [
            line.strip() for line in result.stdout.splitlines()
            if line.startswith(args.pool) and "/" in line
        ]

        verboseprint(f"Filesystems: {filesystems}")

        for fs in filesystems:
            if not fs:
                verboseprint("Warning: Empty filesystem name found, skipping.")
                continue

            snapshot_name = "backup_" + datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%Z")
            snapshot_command = ["sudo", "zfs", "snapshot", f"{fs}@{snapshot_name}"]
            verboseprint(f"Creating snapshot for filesystem: {fs} with command: {' '.join(snapshot_command)}")
            run_cmd(snapshot_command)


        verboseprint("Pruning snapshots")
        for fs in filesystems:
            verboseprint("scanning", fs)
            result = subprocess.run(["zfs", "list", "-H", "-t", "snapshot", "-o", "name"], capture_output=True, text=True, check=True)
            snapshots = [line.split('@')[1] for line in result.stdout.splitlines() if line.startswith(f"{fs}@")]
            snapshots_to_keep = filter_snapshots(snapshots)
            snapshots_to_delete = [s for s in snapshots if s not in snapshots_to_keep]

            delete_snapshots(fs, snapshots_to_delete)

        print(f"Retention policy applied.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    args = parse_arguments()  # Parse arguments
    if args.verbose:
        def verboseprint(*args):
            print(*args)
    else:
        verboseprint = lambda *a: None  # do-nothing function

    main()
