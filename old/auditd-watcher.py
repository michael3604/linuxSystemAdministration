#!/usr/bin/env python3
'''
Licence:
Copyright 2024 Michael Neumeier
Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

For technical documentation please see function "parse_arguments" a bit further down.
'''

import os
import time
import datetime
import subprocess
import argparse
import sys

# Function to set up and handle command-line arguments using argparse
def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Monitor a log file for specific filesystems and execute a script with the filesystem as a parameter when they are found.\n"
                    "  Intended use case: on-demand-snapshots of ZFS filesystems.",
        epilog="Example usage:\n"
               "  sudo 'parser.prog: {}'.format(parser.prog) --script_to_run /path/to/script.py\n"
               "  sudo 'parser.prog: {}'.format(parser.prog) --log_file /var/log/syslog --script_to_run /path/to/script.py --dry-run\n"
               "  sudo 'parser.prog: {}'.format(parser.prog) --common_key 'filesystem-watcher-4pghm3x-' --filesystems /tank/Vms,/tank/data --script_to_run /path/to/script.py\n",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument('-l', '--log_file', default="/var/log/audit/", help='Path to the log file to monitor.')
    parser.add_argument('-k', '--common_key', help='Optional key to look for in the log file to avoid false positives (e.g., "4omnsp0").')
    parser.add_argument('-f', '--filesystems', nargs='+', help='Optional, comma separated list of filesystem names to search for in the log file. If not provided, will use auditctl -l output. Please restart this script to catch new watchers.')
    parser.add_argument('-s', '--script_to_run', required=True, help='Path to the script to execute when a filesystem is found. The filesystem will be added as an argument')
    parser.add_argument('-t', '--interval', type=int, default=30, help='Interval (in seconds) between checks. Default is 30 seconds, minimum is 15 seconds.\n'
                                                                 'Note: The time it takes to run the script is added to the interval.')
    parser.add_argument('--dry-run', action='store_true', help='Enable dry-run mode where no scripts are executed.')
    
    '''
    technical explaination:
        auditd runs independently, monitors the filesystems for changes and writes into a log.
            examples:
            'sudo auditctl -w /tank/data -p w -k filesystem-watcher-4pghm3x-data'
            'sudo auditctl -w /tank/VMs -p w -k filesystem-watcher-4pghm3x-VMs'
            to watch for changes in /tank/data and /tank/VMs and write the
            key filesystem-watcher-4pghm3x-data to the auditd log file. 
            The '4pghm3x' part acts as a identifier against other auditd watchers.
        This script then reads the log created by auditd, looks for the watcher key,
            extracts the name of the snapshot and hand another script with the name
            of the filesystem as a parameter to actually take the snapshot.
        It is highly recommended to automatically validate the result independently.
            E.g. by daily checking the ZFS logs if any snapshots have been made.
        It is also highly recommended to create a daemon and have it restarted daily
            to ensure that new watchers are detected, unless --filesystems is used.
    '''
    
    return parser.parse_args()

# Ensure script is running as root
def check_root_privileges():
    if os.geteuid() != 0:
        sys.exit("This script must be run as root. Exiting.")

# Get list of filesystems using auditctl with a key filter
def get_filesystems_from_auditctl(key_prefix):
    try:
        result = subprocess.run(['auditctl', '-l'], stdout=subprocess.PIPE, check=True, text=True)
        lines = result.stdout.splitlines()
        filesystems = set()
        for line in lines:
            if '-w' in line and key_prefix in line:
                parts = line.split()
                if len(parts) >= 2:
                    filesystems.add(parts[1].strip("/"))  # Second part is the filesystem path
        return list(filesystems)
    except subprocess.CalledProcessError as e:
        sys.exit(f"Failed to retrieve filesystems using auditctl: {e}")

def run_script(script_to_run, fs, dry_run):
    command = [script_to_run, fs]
    if dry_run:
        print(f"DRY-RUN: Command to be executed for {fs}: {' '.join(command)}")
        print(datetime.datetime.now())
    else:
        print(f"Filesystem {fs} found in log. Executing the script: {script_to_run} {fs}")
        subprocess.run(command)

# MAIN loop to periodically check the log file
def monitor_log(log_file, filesystems, script_to_run, interval, common_key, dry_run):
    last_position = 0
    last_size = os.path.getsize(log_file)
    
    while True:
        found_filesystems = set()  # Define the set here before each log scan
        current_size = os.path.getsize(log_file)
        
        # If the file size has decreased, assume log rotation and execute script for all filesystems
        if current_size < last_size:
            print(f"Log file size decreased, likely rotated. Executing the script for all filesystems: {filesystems}")
            for fs in filesystems:
                run_script(script_to_run, fs, dry_run)
            last_position = 0  # Reset position due to log rotation
        else:
            with open(log_file, 'r') as f:
                f.seek(last_position)  # Move to the last checked position
                lines = f.readlines()
            
                for line in lines:  # Reads through the latest additions of the log file
                    if common_key is None or common_key in line: #looks for the common key (if applicable)
                        for fs in filesystems:
                            if fs in line and fs not in found_filesystems: #checks if the script did already ran in this pass.
                                found_filesystems.add(fs)
                                run_script(script_to_run, fs, dry_run)
        
                LAST_position = f.tell()  # Update the file position after reading
        last_size = current_size  # Update the tracked file size
        time.sleep(interval)

if __name__ == '__main__':
    args = parse_arguments()  # Parse command-line arguments
    
    # Enforce minimum interval of 15 seconds
    if args.interval < 15:
        print("Interval too low. Setting to minimum value of 15 seconds.")
        args.interval = 15

    # Ensure root privileges
    check_root_privileges()
    
    # Retrieve filesystems if not provided
    if not args.filesystems:
        print(f"No filesystems provided. Retrieving from auditctl with key prefix '{args.common_key}-'..." if args.common_key else "No filesystems provided. Retrieving from auditctl...")
        args.filesystems = get_filesystems_from_auditctl(args.common_key if args.common_key else '')
        if not args.filesystems:
            sys.exit(f"No filesystems found from auditctl output with key prefix '{args.common_key}-'." if args.common_key else "No filesystems found from auditctl output. Exiting.")
    
    print(f"Monitoring log file: {args.log_file}")
    print(f"Checking for filesystems: {args.filesystems}")
    print(f"Script to execute: {args.script_to_run}")
    print(f"Mimimum interval between checks: {args.interval} seconds")
    
    # Start monitoring the log
    monitor_log(args.log_file, args.filesystems, args.script_to_run, args.interval, args.common_key, args.dry_run)
