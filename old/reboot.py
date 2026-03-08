#!/usr/bin/env python3

import os
import sys
import psutil
import time
import subprocess
import threading

def check_sudo():
        """Check if the script is running with sudo privileges."""
        if os.geteuid() != 0:
                print("This script requires sudo privileges. Please run it with sudo.")
                sys.exit(1)

def is_apt_running():
    """Check if any apt-related process is running.""" 
    for proc in psutil.process_iter(['name']):
        try:
            if 'apt' in proc.info['name']:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False

def wait_for_apt_to_finish():
    """Wait until apt-related processes have finished."""
    print("Checking if apt is running...")
    while is_apt_running():
        print("Apt is running, waiting for 5 seconds...")
        time.sleep(5)
        print("Apt has finished running.")
            
def reboot_server():
    """Reboot the server."""
    print("Rebooting the server...")
    subprocess.run(['sudo', 'reboot'])
                
def reboot_after_timeout(timeout):
    """Reboot the server after a specified timeout in case the system is hung up completely"""
    print(f"Rebooting the server in {timeout / 3600} hours at the latest...")
    time.sleep(timeout)
    reboot_server()

def stop_lxc_containers():
    """Stop all running LXC containers."""
    try:
        result = subprocess.run(['sudo', 'lxc-ls', '--running'], capture_output=True, text=True)
        running_containers = result.stdout.strip().split()
        if running_containers:
            print("Stopping LXC containers...")
            for container in running_containers:
                print(f"Stopping container: {container}")
                subprocess.run(['sudo',  '-u', user76, 'lxc-stop', '-n', container], check=True)
                print("All LXC containers stopped.")
            else:
                print("No running LXC containers found.")
    except subprocess.CalledProcessError as e:
        print(f"An error occurred while stopping LXC containers: {e}")
        
if __name__ == "__main__":

    check_sudo()
    
    # Set the timeout to 3 hours (10800 seconds)
    timeout = 10800
    
    # Stop running LXC containers
    stop_lxc_containers()
    
    # Start the timeout thread
    timeout_thread = threading.Thread(target=reboot_after_timeout, args=(timeout,))
    timeout_thread.start()
    
    # Wait for apt to finish, but the timeout thread will enforce the 3-hour limit
    wait_for_apt_to_finish()
    
    # Ensure the server reboots if apt finishes before the timeout
    reboot_server()
