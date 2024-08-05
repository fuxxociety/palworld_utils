from rcon import rcon_client
from utility.util import check_for_process, kill_process
import math
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta

import psutil

from utility.config import *
from utility.detect_api import run_command
from utility.logging_config import setup_logger, log_error, log_info, os_platform

game_path = None
backups_path = None
num_players = None
is_local = None


# TODO: copy the rest_api_port from detect_api.py if it exists for re-use
def game_local():
    global is_local
    try:
        if not os_platform == 'win32':
            ip_result = subprocess.check_output("hostname -I", shell=True).decode().strip()
            local_ip_addresses = ip_result.split()
            if SERVER_IP in local_ip_addresses:
                is_local = True
            else:
                is_local = False
        else:
            ip_result = subprocess.check_output("ipconfig", shell=True).decode()
            local_ip_addresses = []
            for line in ip_result.split('\n'):
                if "IPv4 Address" in line:
                    ip_address = line.split(':')[1].strip()
                    local_ip_addresses.append(ip_address)
            if SERVER_IP in local_ip_addresses:
                is_local = True
            else:
                is_local = False
    except Exception as ex:
        exit(f"Error getting IP addresses: {ex}")


def set_backup_dir():
    global backups_path
    if os_platform != 'win32':
        # set up OS-Specific paths
        backups_path = BACKUPS_PATH
    else:
        backups_path = f"{os.path.join(os.getenv('USERPROFILE'), 'Desktop')}"
    return backups_path


def set_gamesave_dir():
    global game_path
    if os_platform != 'win32':
        game_path = GAMESAVE_PATH
    else:
        game_path = f"{os.path.join(os.getenv('USERPROFILE'), 'Desktop', 'Palworld')}"
    return game_path


# Function to check directory existence and permissions
def check_folders(directory, operation):
    operation_map = {
        'r': os.R_OK,
        'w': os.W_OK
    }
    if operation not in operation_map:
        log_error(f"Invalid operation: {operation}. Valid operations are 'r', and 'w'.")
        exit(1)

    # Check if paths are valid
    if not os.path.exists(directory):
        try:
            os.makedirs(directory, exist_ok=True)
            log_info(f"Creating {directory} .")
        except OSError as e:
            log_error(f"Failed to create directory {directory}:{e}")
            sys.exit(1)
    elif not os.path.isdir(directory):
        log_error(f"Path {directory} exists but is not a directory.")
        sys.exit(1)

    if operation == 'w':
        if not os.access(directory, os.W_OK):
            log_error(f"{directory} is not writable.")
            sys.exit(1)
    elif operation == 'r':
        if not os.access(directory, os.R_OK):
            log_error(f"{directory} is not readable.")
            sys.exit(1)
    return True


def convert_size(size_bytes):
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return "%s %s" % (s, size_name[i])


# Function to calculate average backup size, skipping the most recent backup
def calculate_average_backup_size(backup_dir):
    backup_files = [os.path.join(backup_dir, f) for f in os.listdir(backup_dir)
                    if f.startswith("Palworld_") and f.endswith(".tar.gz")]
    if not backup_files:
        return 0
    # Sort files by creation time oldest first
    backup_files.sort(key=os.path.getctime)
    # Skip the most recent backup (last in the list)
    backup_files = backup_files[:-1]
    # Calculate total size of backups (excluding the most recent one)
    total_size = sum(os.path.getsize(f) for f in backup_files)
    # Calculate average size
    average_size = total_size / len(backup_files) if len(backup_files) > 0 else 0
    return average_size


# Function to check available disk space
def check_disk_space():
    if os_platform != 'win32':
        statvfs = os.statvfs(GAMESAVE_PATH)
        free_space = statvfs.f_frsize * statvfs.f_bfree
    else:
        usage = psutil.disk_usage(os.getenv('USERPROFILE'))
        free_space = usage.free
    return free_space


# Function to calculate expected backup size
def expected_backup_size(backup_dir):
    backup_files = [os.path.join(backup_dir, f) for f in os.listdir(backup_dir)
                    if f.startswith("Palworld_") and f.endswith(".tar.gz")]
    if not backup_files:
        return 0

    # Sort files by creation time oldest first
    backup_files.sort(key=os.path.getctime)

    # Skip the most recent backup (last in the list)
    backup_files = backup_files[:-1]

    # Calculate total size, in bytes, of backups (excluding the most recent one)
    total_size = sum(os.path.getsize(f) for f in backup_files)

    # Calculate average size
    expected_size = total_size / len(backup_files) if len(backup_files) > 0 else 0

    return expected_size


def compress_backup(input_folder, output_file):
    log_info("Starting Palworld backup.")
    try:
        # subprocess.run(["tar", "-czf", output_file, "-C", input_folder, "."]
        #               check = True, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        subprocess.run(["tar", "-czf", output_file, "-C", input_folder, "."],
                       text=True, check=True, capture_output=True
                       )
        # Output the result (stdout and stderr)
        log_info(f"Backup created: {output_file}")
        return True
    except FileNotFoundError:
        log_error("Error: 'tar' executable not found. Please ensure it is installed.")
        sys.exit(1)  # Exit with status code 1 indicating an error
    except subprocess.CalledProcessError as e:
        log_error(f"Abort: Tar process failed with error: {e}")
        return False
    except Exception as e:
        log_error(f"Unexpected error: {e}")
        return False


# Function to start the Palworld service
def start_service(timeout=10):
    log_info("Starting Palworld service.", end="")
    if is_local:
        try:
            result = subprocess.Popen(['sudo', 'systemctl', 'start', 'palworld.service'],
                                      stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE,
                                      text=True
                                      )
            stdout, stderr = result.communicate(timeout=timeout)
            if result.returncode == 0:
                if check_if_running(timeout=timeout, expect_running=True):  # True if the server is in expected state
                    return True
                else:
                    # server did not start
                    log_error(f"\nStart command failed.")
                    return False
            else:
                log_error(f"\nPalworld service failed to start.")
        except subprocess.TimeoutExpired:
            # Handle timeout
            result.kill()
            stdout, stderr = result.communicate()
            log_error(f"\nStarting Palworld service timed out: %s", stderr)

        except Exception as e:
            # Handle other exceptions
            log_error(f"\nAn unexpected error occurred: %s", str(e))
    else:
        cmd_result = run_command("start", timeout=timeout)
        if cmd_result:
            if check_if_running(timeout=timeout, expect_running=True):  # True if the server is in expected state
                return True
            else:
                # server did not start
                log_error(f"\nStart command failed.")
                return False
        else:
            from utility.detect_api import data
            log_error(f"\nRemote start command failed: {data}")
            return False
    log_info(f"\nPalworld service started successfully.")


# Function to restart the Palworld service
def restart_service(timeout):
    """
    Restarts the Palworld server process.
    Args:
        timeout (int): Time, in seconds, to wait for the restart process to complete.
    Returns:
        boolean: True, after the save finishes.
    """
    if save_world():
        log_info("Restarting Palworld server ", end="")
        if is_local:
            log_info("locally.")
            if check_if_running(expect_running=True):  # True if the server is in expected state
                result = subprocess.Popen(['sudo', 'systemctl', 'restart', SERVICE_NAME],
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                try:
                    stdout, stderr = result.communicate(timeout=timeout)
                    if result.returncode == 0:
                        # Check service status
                        service_status = subprocess.run(['systemctl', 'is-active', SERVICE_NAME],
                                                        capture_output=True, text=True)
                        if service_status.stdout.strip() == 'active':
                            log_info("Palworld restart is complete.")
                        else:
                            log_error("Failed to verify Palworld server is running.")
                    else:
                        log_error(f"Error restarting Palworld service: {stderr.decode()}")
                except subprocess.TimeoutExpired:
                    result.kill()
                    stdout, stderr = result.communicate()
                    log_error(f"Palworld service restart timed out: {stderr.decode()}")
            else:
                log_info("Server is not running.")
        else:
            log_info("remotely.")
            cmd_result = run_command("restart", timeout=timeout)
            if cmd_result:
                if check_if_running(timeout=timeout, expect_running=False):  # True if the server is in expected state
                    log_info("Palworld restart is complete.")
                    return True
                else:
                    # server did not start
                    log_error(f"Restart command failed.")
                    return False
            else:
                from utility.detect_api import data
                log_error(f"Remote restart command failed with errors:\n{data}")
                return False


def save_world():
    """
    Saves the world.
      Only available if requested over RCON or REST API.
    Returns:
        boolean: True, after the save finishes.
    """
    if check_if_running(expect_running=True, timeout=30):  # False if server is NOT running
        log_info("Saving Palworld world.")
        if not run_command("save") == 200:
            sys.exit("Error sending save command.")
        else:
            log_info("Game was saved.")
            return True
    else:
        log_info("Timed out trying to save.")
        return True


# Function to handle the shutdown logic
def online_players(max_duration_seconds):
    """
    Every second, returns the number of players currently logged in, for (n) seconds.
    Exits immediately if no players are online.
    Args:
        max_duration_seconds (int): The maximum time to poll for the status.
    Returns:
        int: Number of players.
    """
    start_time = time.time()
    end_time = start_time + max_duration_seconds
    global num_players

    while time.time() < end_time:
        response = run_command("players")
        if response:
            from utility.detect_api import data
            if response == 200 and data:
                num_players = len(data.get('players', []))
            else:
                log_error("Failed to retrieve player data.")
        else:
            log_error("rcon error")
            sys.exit(1)
        time.sleep(60)  # Check every minute
    log_info("Maximum duration reached. Giving up until next interval.")
    return False


# Function to shut down the server
def stop_service(wait_time):
    """
    Stops the palworld service.
    Args:
        wait_time (int): Waits (n) seconds for the server to stop.
    Returns:
        boolean: True if the server is stopped.
    """
    log_info("Shutting down Palworld server.", end="")
    if check_if_running(expect_running=True, timeout=2):
        if is_local:
            response = subprocess.Popen(['sudo', 'systemctl', 'shutdown', SERVICE_NAME],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                stdout, stderr = response.communicate()
                if response.returncode == 0:
                    # Check service status
                    service_status = subprocess.run(['systemctl', 'is-active', SERVICE_NAME],
                                                    capture_output=True, text=True)
                    if service_status.stdout.strip() == 'active':
                        log_info("Palworld shutdown is complete.")
                        return True
                    else:
                        log_error("Failed to verify Palworld server is stopped.")
                        return False
                else:
                    log_error(f"Error shutting down Palworld service: {stderr.decode()}")
                    return False
            except subprocess.TimeoutExpired:
                response.kill()
                stdout, stderr = response.communicate()
                sys.exit(f"Palworld service shutdown timed out: {stderr.decode()}")

        else:
            # Separate the palworld shutdown command wait_time from the script's timeout.
            palworld_wait_time = 1
            response = run_command("shutdown", palworld_wait_time, "shutdown")
            if response == 200:
                if check_if_running(timeout=wait_time, expect_running=False):  # True if the server is in expected state
                    log_info(f"\nServer shutdown successful.")
                    return True
                else:
                    sys.exit(f'Unexpected response sending shutdown command.')
    else:
        log_info("Palworld is not running or unreachable.")
        return True


def kill_service():
    if is_local:
        # TODO: verify successful output from command
        subprocess.Popen(['sudo', 'systemctl', 'kill', 'palworld.service'])
    else:
        # TODO: add remote kill capability
        1 == 1
    return True


# Function to wait for service to stop
# Returns True if running, False if stopped or not available
def check_if_running(expect_running, timeout=10):
    """
    Polls to check if the server status matches the expected state.
    Args:
        timeout (int): The maximum time to poll for the status.
        expect_running (bool): True if you expect the server to be running, False otherwise.
    Returns:
        bool: Will become True if the server is in the expected state within the timeout, False otherwise.
    """
    # TODO: This command should eventually produce no visible output
    #   true/false/fail for current status
    end_time = time.time() + timeout
    while time.time() < end_time:
        if is_local:
            # game running on localhost
            try:
                result = subprocess.run(
                    ['systemctl', 'is-active', 'palworld.service'],
                    capture_output=True, text=True, check=True
                )
                status = result.stdout.strip()
                if status == 'inactive':
                    # Service is inactive
                    return False
                elif status == 'active':
                    # Service is still running
                    pass
                else:
                    # Unexpected output
                    log_info("check_if_running: Unexpected output")
                    return "Fail"
            except subprocess.CalledProcessError:
                # Handle the case where 'systemctl' fails (e.g., service does not exist)
                log_error("Service unit palworld.service does not exist.")
                return "Fail"
        else:
            # TODO: If this remote command returns an error, handle gracefully
            #   this code expects any error are squashed
            status = run_command("status", timeout=timeout)
            # successful 'status' should be "200"
            if (status == 200 and expect_running) or (status != 200 and not expect_running):
                return True

            log_error(".", end="")
            # loop should continue for next interval
        time.sleep(1)  # Poll every half-second
    log_error(f"Timed out waiting for palworld.service to stop.")
    return False


def backup_process():
    global game_path
    global backups_path

    # Check folder presence and free space
    game_path = set_gamesave_dir()
    if not check_folders(game_path, "r"):
        sys.exit(1)

    backups_path = set_backup_dir()
    if not check_folders(backups_path, "w"):
        sys.exit(1)

    # Calculate expected backup size
    average_backup_size = calculate_average_backup_size(set_backup_dir())
    required_space = 2 * average_backup_size

    if not check_disk_space() >= required_space:
        log_error("Not enough free space for a new backup.")
        return

    # Perform backup
    backup_file = os.path.join(backups_path, f"Palworld_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.tar.gz")
    tar_results = compress_backup(game_path, backup_file)
    if not tar_results:
        # Error compressing file
        start_service(10)
        exit(1)
    # Initialize variables
    paths_to_delete = []  # Initialize paths_to_delete list
    current_date = datetime.now()
    backups_by_day = {}

    # Organize backups by date using filename date
    for file in os.listdir(backups_path):
        if file.startswith("Palworld_") and file.endswith(".tar.gz"):
            file_path = os.path.join(backups_path, file)
            match = re.search(r"Palworld_(\d{4}-\d{2}-\d{2})_\d{2}-\d{2}-\d{2}.tar.gz", file)
            if match:
                date_str = match.group(1)
                if date_str not in backups_by_day:
                    backups_by_day[date_str] = []
                backups_by_day[date_str].append(
                    (datetime.strptime(match.group(0), "Palworld_%Y-%m-%d_%H-%M-%S.tar.gz"), file_path))

    # Sort backups by creation time within each day
    for date_str in backups_by_day:
        backups_by_day[date_str].sort()

    # Keep the most recent two backups from today
    today_str = current_date.strftime('%Y-%m-%d')
    if today_str in backups_by_day:
        delete_today = backups_by_day[today_str][:-2]  # Delete the rest for today
        paths_to_delete.extend([file_path for _, file_path in delete_today])

    # Keep the most recent backup for each day within the configured DAYS_TO_KEEP
    for i in range(1, int(DAYS_TO_KEEP) + 1):
        day_str = (current_date - timedelta(days=i)).strftime('%Y-%m-%d')
        if day_str in backups_by_day:
            delete_day = backups_by_day[day_str][:-1]  # Delete the rest for this day
            paths_to_delete.extend([file_path for _, file_path in delete_day])

    # Delete the collected old backups
    for file_path in paths_to_delete:
        os.remove(file_path)
        log_info(f"Deleted old backup: {file_path}")
    log_info("Backup process complete, ", end="")


# Main script logic
if __name__ == "__main__":
    logger = setup_logger()
    game_local()
    if len(sys.argv) > 1 and sys.argv[1] == "--backup":
        log_info("Checking server status.")
        stop_service(15)
        backup_process()
        start_service()
    if len(sys.argv) > 1 and sys.argv[1] == "--status":
        run_command("status")
    if len(sys.argv) > 1 and sys.argv[1] == "--info":
        run_command("info")
    if len(sys.argv) > 1 and sys.argv[1] == "--players":
        run_command("players")
    if len(sys.argv) > 1 and sys.argv[1] == "--settings":
        run_command("settings")
    if len(sys.argv) > 1 and sys.argv[1] == "--metrics":
        run_command("metrics")
    if len(sys.argv) > 1 and sys.argv[1] == "--announce":
        run_command("announce", "testing")
    if len(sys.argv) > 1 and sys.argv[1] == "--kick":
        run_command("kick", "steam_00000000000000000")
    if len(sys.argv) > 1 and sys.argv[1] == "--ban":
        run_command("ban", "steam_00000000000000000")
    if len(sys.argv) > 1 and sys.argv[1] == "--save":
        log_info("Saving palworld game.")
        run_command("save")
    if len(sys.argv) > 1 and sys.argv[1] == "--start":
        if start_service():
            log_info("Server started successfully.")
    if len(sys.argv) > 1 and sys.argv[1] == "--restart":
        if restart_service(20):
            log_info("Server started successfully.")
    if len(sys.argv) > 1 and sys.argv[1] == "--stop":
        stop_service(10)
    if len(sys.argv) > 1 and sys.argv[1] == "--force_stop":
        log_info("Killing palworld server forcefully.")
        kill_service()
