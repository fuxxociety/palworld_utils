# config.py

# Server details
SERVER_IP = '127.0.0.1'
RCON_PORT = 25575
REST_PORT = 8212  # default: 8212

# 'True' if using a custom wrapper for REST
WRAPPER = True

# Authentication
ADMIN_USER = "admin"  # 'admin' by default
ADMIN_PASS = "adminpassword"  # configured in palworld config

# Service name for systemd operations
SERVICE_NAME = 'palworld.service'

# Palworld Save path
GAMESAVE_PATH = "/home/steam/Steam/steamapps/common/PalServer/Pal/Saved/SaveGames/0"

# Backups path
BACKUPS_PATH = "/home/steam/Palworld_backups"

# Keep this many days of backups
DAYS_TO_KEEP = 3
