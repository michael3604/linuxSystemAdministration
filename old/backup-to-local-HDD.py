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
import subprocess
import argparse
import sys

# Function to set up and handle command-line arguments using argparse
def parse_arguments():
    parser = argparse.ArgumentParser(
        description="creating backups from snapshots using hardlinks for versioning.\n"
                    "  Intended use case: backups of ZFS filesystems.",
        epilog="Example usage:\n"
               "  sudo 'parser.prog: {}'.format(parser.prog) sudo /scripts/backup-to-local-HDD.py -v -s /tank/test -t /mnt/ext-HDD/data/test\n"
               "  sudo 'parser.prog: {}'.format(parser.prog) sudo /scripts/backup-to-local-HDD.py -v -s /tank/test -t /mnt/ext-HDD/data/test -S .zfs/snapshot -p backup_ \n",
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument('-s', '--source',  required=True, help='source of backup e.g. "/tank/nextcloud"')
    parser.add_argument('-S', '--subdir',                 help='subdirectory within source. e.g. ".zfs/snapshot"')
    parser.add_argument('-p', '--prefix',                 help='prefix of source folder. "e.g. backup_"')
    parser.add_argument('-t', '--target',  required=True, help='target of backup e.g. /mnt/ext-HDD')
    parser.add_argument('-v', '--verbose', action='store_true', help='enable verbose output')
    parser.add_argument(      '--dry-run', action='store_true', help='Enable dry-run mode where no scripts are executed.')

    '''
    technical explaination:
	###ToDo
    '''

    return parser.parse_args()

# Ensure script is running as root
def check_root_privileges():
    if os.geteuid() != 0:
        sys.exit("This script must be run as root. Exiting.")

# dry-run
def run_cmd(command, dry_run):
    if dry_run:
        verboseprint("D R Y   R U N! not executing " + command)
    else:
        verboseprint("executing " + command)
        subprocess.run(command, shell = True, executable="/bin/bash")

def get_last_folder(dir, prefix=None):
    # Check if the target directory exists and is a directory
    if not os.path.isdir(dir):
        raise FileNotFoundError(f"The directory {dir} does not exist.")

    # Get a list of directories in the target directory, optionally filtered by prefix                                                       
    folders = [
        d for d in os.listdir(dir)
        if os.path.isdir(os.path.join(dir, d)) and d.startswith(prefix)
    ]

    # Return the alphabetically last directory
    if folders:
        last_folder = sorted(folders)[-1]
        verboseprint("last folder in " + dir + " is " + last_folder)
        return last_folder
    else:
        raise ValueError(f"No folders starting with '{prefix}' found in {dir}.")

def delete_inwork_folders(folder_path):
    """
    Deletes every subfolder within the specified folder that ends with .inwork.

    Parameters:
    folder_path (str): Path to the parent folder.
    """
    try:
        # Walk through all directories within the given folder
        for root, dirs, files in os.walk(folder_path):
            for dir_name in dirs:
                # Check if the subfolder name ends with '.inwork'
                if dir_name.endswith('.inwork'):
                    dir_path = os.path.join(root, dir_name)
                    run_cmd("rm -r " + dir_path, args.dry_run)  # Delete the folder and its contents ###ToDo: Raise warning
        verboseprint("All '.inwork' folders have been deleted.")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == '__main__':
    args = parse_arguments()  # Parse command-line arguments

    # Ensure root privileges
    # check_root_privileges()

    #Todo: lock file in /var/lock

    #verbosity
    if args.verbose:
        def verboseprint(*args):
        # Print each argument separately so caller doesn't need to
        # stuff everything to be printed into a single string
            for arg in args:
               print (arg),
            print
    else:
        verboseprint = lambda *a: None      # do-nothing function

    # Construct the path to the specified subdirectory
    if args.subdir:
         source_main_folder = os.path.join(args.source, args.subdir)
    else:
         source_main_folder = args.source
    verboseprint("Source Main Folder = " + source_main_folder)

    #cleanup previous failed backup
    delete_inwork_folders(args.target)

    #find folders
    source_sub_folder=get_last_folder(source_main_folder, args.prefix) #get latest snapshot of source
    source_folder=os.path.join(source_main_folder,source_sub_folder) #absolute path of latest snapshot of source
    verboseprint("source folder: " + source_folder)

    #getting last backup (creating a dummy if necessary)
    last_backup_sub = None
    for z in range(3):
        try:
            last_backup_sub = get_last_folder(args.target, args.prefix) #last backup on target
            break
        except:
            dummybackup=os.path.join(args.target,"backup_1900-01-01T00:00:00-UTC")
            run_cmd("mkdir -p " + dummybackup, args.dry_run)
    last_backup=os.path.join(args.target, last_backup_sub)
    verboseprint("last backup: " + last_backup)

    #getting new backup
    new_backup=os.path.join(args.target, source_sub_folder)
    new_backup_inwork=os.path.join(new_backup + ".inwork")
    verboseprint("new backup: " + new_backup)

    #backup
    run_cmd("rsync -av --link-dest " + last_backup + " " + source_folder + "/ " +  new_backup_inwork, args.dry_run)
    run_cmd("mv "+ new_backup_inwork +" " + new_backup, args.dry_run)
