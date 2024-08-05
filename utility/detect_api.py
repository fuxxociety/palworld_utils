import argparse
import base64
import json

import requests

from utility.config import *
from rcon import rcon_command
from utility.logging_config import setup_logger, log_info, log_error

# Constants
payload = {}
headers = None
status = None
data = None
text = None

baseurl = f"http://{SERVER_IP}:{REST_PORT}/v1/api/"

# Define valid commands and their descriptions
valid_commands = {
    "info": "Display server info",
    "status": "Returns True/False if server is responding",
    "players": "List online players",
    "settings": "Show server settings",
    "metrics": "Show server metrics",
    "save": "Save the server state",
    "stop": "Stop the server",
    "force-stop": "Forcefully stop the server",
    "kick": "Kick a player",
    "ban": "Ban a player",
    "unban": "Unban a player",
    "announce": "Make an announcement"
}


def send_get_request(command):
    global status
    global data
    global text
    global headers
    response = None
    status_convert = None

    try:
        headers = {
            'Accept': 'application/json',
            'Authorization': f'Basic {base64.b64encode(f"{ADMIN_USER}:{ADMIN_PASS}".encode()).decode()}'
        }
        # command "status" doesnt exist, use 'info' to get a valid response
        status_convert = False
        if command in ["status"]:
            command = command[:-len('status')] + 'info'
            status_convert = True
        # with requests.get, requests do not time out
        response = requests.get(f"{baseurl}{command}", headers=headers, data=payload)
        # {info, players, metrics, settings}
        response.raise_for_status()
        """On a successful reply, these fields are populated
        response.ok = True
        response.reason = 'OK'
        response.status_code = 200
        response.text = <json encoded string>
        response.content = bytes object(of json-encoded string)"""
        if response.content:
            try:
                data = json.loads(response.content)
                # Check if the parsed data is non-empty
                if data:
                    return response.status_code
                else:
                    print("Received empty JSON object.")
            except json.JSONDecodeError as e:
                print("Failed to decode JSON:", e)
        else:
            print("No content received.")

    except requests.exceptions.HTTPError as http_err:
        if http_err.response.status_code == 400:
            if not status_convert:
                print("400 Bad Request")
        elif http_err.response.status_code == 401:
            print("401 Access denied.")
        elif http_err.response.status_code == 404:
            print("404 Unavailable.")
        elif http_err.response.status_code == 500:
            data = json.loads(response.text).get('message')
            if command in "info":
                return
            else:
                print(f"500 Server error {data}.")
        else:
            print(f"HTTP error: {http_err}")
        return False

    except requests.exceptions.ConnectionError as conn_err:
        if not status_convert:
            if "refused" in str(conn_err):
                print("Connection Refused")
            print(f"{conn_err}")
        return False
    except requests.exceptions.Timeout as timeout_err:
        if not status_convert:
            print(f"Timeout error occurred: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        if not status_convert:
            print(f"Request error occurred: {req_err}")
    except json.JSONDecodeError as json_err:
        if not status_convert:
            print(f"Error decoding JSON response: {json_err}")
    return None


# Send command, reply is status successful/unsuccessful
def send_post_request(postcmd):
    global data
    global headers
    response = None

    try:
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Basic {base64.b64encode(f"{ADMIN_USER}:{ADMIN_PASS}".encode()).decode()}'
        }
        # Don't set a timeout, the save command will hang until the server finishes.
        response = requests.post(f"{baseurl}{postcmd}", headers=headers, data=payload)
        # {announce, kick, ban, unban, save, shutdown, stop}
        response.raise_for_status()  # This will raise an HTTPError for bad responses (4xx and 5xx)
        return response.status_code

    except requests.exceptions.HTTPError as http_err:

        if http_err.response.status_code == 400:
            data = f"HTTP Error 400: {response.text}"
        elif http_err.response.status_code == 401:
            data = f"HTTP Error 401: {response.text}"
            print("HTTP Error 401: Unauthorized.")
        elif http_err.response.status_code == 500:
            data = json.loads(response.text).get('message')
            if postcmd in "info":
                return
            else:
                print(f"HTTP Error 500: {data}.")
        else:
            data = response.text
            print(f"HTTP error: {http_err}")

    except requests.exceptions.ConnectionError as conn_err:
        print(f"{conn_err}")
        exit(1)
    except requests.exceptions.Timeout as timeout_err:
        print(f"Timeout error occurred: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        print(f"Request error occurred: {req_err}")
    except json.JSONDecodeError as json_err:
        print(f"Error decoding JSON response: {json_err}")

    return False


def run_command(command, *args, timeout=10):
    global payload
    global status
    global data

    # TODO: If returning a status_code of != 200, log the error and exit
    #  Unless the command is 'info' or 'status'
    rest_api_port = REST_PORT
    if rest_api_port:
        if command in ["players", "info", "status", "settings", "metrics"]:
            # No arguments are accepted.
            if not len(args) == 0:
                log_error("This command does not recognize any arguments.")
                return False
            else:
                status = send_get_request(command)  # should return the HTTP error code, "200" for successful
        elif command == "start":
            # No arguments are accepted from palworld
            if not len(args) == 0:
                log_error("This command does not recognize any arguments.")
                return False
            else:
                if not WRAPPER:
                    # POST: palworld REST API: no json to send, no json response
                    payload = {}
                else:
                    # POST: wrapper REST API: <timeout> is a valid argument
                    payload = json.dumps({"timeout": timeout})
                status = send_post_request(command)
        elif command == "force-stop":
            # No arguments are accepted.
            if not len(args) == 0:
                log_error("This command does not recognize any arguments.")
                return False
            else:
                # POST: no json to send, no json response
                payload = {}
                status = send_post_request(command)
        elif command == "announce":
            if not len(args) == 1:
                log_error(f"The 'announce' command requires exactly one <message> argument.")
                return False
            else:
                # POST: use json to send the message, no json response
                payload = json.dumps({"message": args[0]})
                status = send_post_request(command)
        elif command == "unban":
            if not len(args) == 1:
                log_error(f"The 'unban' command requires exactly one <steam_id> argument.")
                return False
            else:
                # POST: use json to send the message, no json response
                payload = json.dumps({"userid": args[0]})
                status = send_post_request(command)
        elif command == "save":
            if not len(args) == 0:
                log_error("This command does not recognize any arguments.")
                return False
            else:
                # POST: no json to send, no json response
                payload = {}
                status = send_post_request(command)
        elif command == "shutdown":
            if not len(args) == 2:
                log_error(f"The 'shutdown' command requires exactly two arguments (wait_time and message).")
                return False
            else:
                # Check and rearrange args if necessary
                if isinstance(args[0], int) and isinstance(args[1], str):
                    wait_time, msg_txt = args[0], args[1]
                elif isinstance(args[0], str) and isinstance(args[1], int):
                    wait_time, msg_txt = args[1], args[0]
                else:
                    log_error(f"wait_time has to be an integer.")
                    return False
                # POST: use json to send the message, no json response
                payload = json.dumps({"waittime": wait_time, "message": msg_txt})
                status = send_post_request(command)
        elif command == "kick":
            # steam_id required, message_text optional.
            if len(args) == 1:
                steam_id = args[0]
                message_text = "Go away."
            elif len(args) == 2:
                steam_id = args[0]
                message_text = args[1]
            elif len(args) >= 3:
                log_error(f"Too many arguments for the '{command}' command.")
                return False
            else:
                log_error(f"SteamID is required for the '{command}' command.")
                return False
            # POST: use json to send the message, no json response
            payload = json.dumps({"userid": steam_id, "message": message_text})
            status = send_post_request(command)
        elif command == "ban":
            # steam_id required, message_text optional.
            if len(args) == 1:
                steam_id = args[0]
                message_text = "You are banned."
            elif len(args) == 2:
                steam_id = args[0]
                message_text = args[1]
            elif len(args) >= 3:
                log_error(f"Too many arguments for the '{command}' command.")
                return False
            else:
                log_error(f"SteamID is required for the '{command}' command.")
                return False
            # POST: use json to send the message, no json response
            payload = json.dumps({"userid": steam_id, "message": message_text})
            status = send_post_request(command)
        return status  # should return the HTTP error code, "200" for successful
    else:
        # TODO: Verify rcon binary exists before sending commands.
        rcon_command.send_rcon_command(command)
        if command == "save":
            # RCON does not provide feedback. Give it lots of time to make sure the save is complete
            log_info(f"Waiting 2 minutes to allow save to finish.")
            return timeout


logger = setup_logger()
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Handle server commands")
    parser.add_argument('command', nargs='?', help="The command to send to the server")
    args = parser.parse_args()

    if args.command in valid_commands:
        run_command(args.command)
    else:
        log_info("Palworld Utility Tool")
        log_info("This tool sends commands using REST API calls if the REST API is enabled.")
        log_info("Otherwise, the RCON utility is used for server communication.")
        log_info("Usage: python detect_api.py <command>\n")
        log_info("Valid commands:")
        for cmd, desc in valid_commands.items():
            log_info(f"{cmd}: {desc}")
