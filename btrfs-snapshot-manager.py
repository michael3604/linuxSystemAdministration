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
    class CustomFormatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawTextHelpFormatter): #so \n works for newlines and f ... {parser.prog} works for filename
        pass
    parser = argparse.ArgumentParser(formatter_class=CustomFormatter)
    parser.description="creates btrfs snapshots with ISO timestamp, mounts and prunes them."
    parser.epilog=(
        "Example usage:\n"
        f"  sudo {parser.prog} \n"
        f"  sudo {parser.prog} -f /temp -t /mnt/temp-snapshots -d 8\n"
    )
    
    '''
    technical documentation:
    basic idea:
    1) create a read only snapshot named after ISO Date and Time and mount it
    2) prune the snapshots, keeping the youngest ones, some weeks and some month
    this can be used e.g. to create snapshots for backups or as 
    '''
    parser.add_argument('-f', '--filesystem',  default="/", help='btrfs filesystem. e.g. "/home" or "/"')
    parser.add_argument('-b', '--mountpointbasefolder',  default="/mnt/root-snapshots", help='basefolder of the snapshot e.g. "/mnt/home-snapshots"')
    parser.add_argument('-d', '--days',    default=15, type=int, help='number of days a snapshot is kept')
    parser.add_argument('-w', '--weeks',   default=4, type=int, help='number of weeks for which one snapshot each is kept')
    parser.add_argument('-m', '--months',  default=6, type=int, help='number of month for which one snapshot each is kept')
    parser.add_argument('-v', '--verbose', action='store_true', help='enable verbose output')
    parser.add_argument(      '--dry-run', action='store_true', help='enable dry-run mode where no scripts are executed.')
    parser.add_argument(      '--writeable', action='store_true', help='make the snapshots writeable.')

    return parser.parse_args()

# (dry-)run commands and verbosity
def run_cmd(command): #, dry-run):
    command_str = ' '.join(command) if isinstance(command, list) else command # turn into string if necessary
    if args.dry_run:
        verboseprint(f"D R Y   R U N! not executing {command_str}")
    else:
        verboseprint(f"Executing {command_str}")
        subprocess.run(command_str, shell=True, check=True, executable="/bin/bash")

def parse_snapshot_name(snapshot_name):
    try:
        return datetime.strptime(snapshot_name, "%Y-%m-%dT%H:%M:%S%Z")
    except ValueError:
        return None

def filter_snapshots(snapshots):
    snapshots.sort()  # Sort by date

    keepers = [] # reset

    now = datetime.now()

    for snapshot in snapshots:
        snapshot_date = parse_snapshot_name(snapshot)
        if not snapshot_date:
            verboseprint(snapshot, " cannot be processed and will therefore be kept.")
            keepers.append(snapshot)
            continue

        # ToDo: Change to step-width approach
        # Daily retention
        if snapshot_date >= now - timedelta(days=args.days):
            verboseprint(snapshot, "will be kept")
            keepers.append(snapshot)
            continue

        # Weekly retention
        if snapshot_date >= now - timedelta(weeks=args.weeks):
            if all(abs((snapshot_date - parse_snapshot_name(kept)).days) >= 7 for kept in keepers):
                verboseprint(snapshot, "will be kept")
                keepers.append(snapshot)
                continue

        # Monthly retention
        if snapshot_date >= now - timedelta(weeks=args.months * 4):
            if all(snapshot_date.month != parse_snapshot_name(kept).month or snapshot_date.year != parse_snapshot_name(kept).year for kept in keepers):
                verboseprint(snapshot, "will be kept")
                keepers.append(snapshot)
                continue

        verboseprint(snapshot, "will be removed")
    return keepers

def delete_snapshots(base_path, snapshots_to_delete):
    for snapshot in snapshots_to_delete:
        snapshot_path = os.path.join(base_path, snapshot)
        try:
            print(f"Deleting snapshot: {snapshot_path}")
            run_cmd(["btrfs subvolume delete", snapshot_path])
        except subprocess.CalledProcessError as e:
            print(f"Failed to delete snapshot {snapshot_path}: {e}")

def main():
    if not os.path.exists(args.mountpointbasefolder):
        os.makedirs(args.mountpointbasefolder)
    verboseprint("Create and mount btrfs snapshot")
    if args.writeable:
        readOnlyFlag=""
    else:
        readOnlyFlag="-r"
    run_cmd(["btrfs", "subvolume", "snapshot", readOnlyFlag, args.filesystem, os.path.join(args.mountpointbasefolder, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%Z"))]) # the timezone.utc part is important for %Z to not be empty.
    verboseprint("Prune snapshots")
    try:
        snapshots = [entry for entry in os.listdir(args.mountpointbasefolder) if os.path.isdir(os.path.join(args.mountpointbasefolder, entry))]
        snapshots_to_keep = filter_snapshots(snapshots)
        snapshots_to_delete = [s for s in snapshots if s not in snapshots_to_keep]

        delete_snapshots(args.mountpointbasefolder, snapshots_to_delete)

        print(f"Retention policy applied. {len(snapshots_to_delete)} snapshots deleted.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    args = parse_arguments()  # Parse arguments
    # define verboseprint
    if args.verbose:
        def verboseprint(*args):
            print (*args)
    else:
        verboseprint = lambda *a: None  # do-nothing function

    main()
