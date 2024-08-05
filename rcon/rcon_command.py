import subprocess

from utility import config


def send_rcon_command(command):
    # rcon commands have no output, so code is much simpler
    baseurl = f"{config.SERVER_IP}:{config.RCON_PORT}"
    formatted_cmd = f"/{command}"
    result = subprocess.run(
        ["rcon", "-a", baseurl, "-p", config.ADMIN_PASS, "-t", "rcon", formatted_cmd],
        capture_output=True,
        text=True
    )
    print(result.stdout.strip())
