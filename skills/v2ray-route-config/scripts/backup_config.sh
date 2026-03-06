#!/bin/bash
# Create timestamped backup of V2Ray config file

if [ $# -ne 1 ]; then
    echo "Usage: $0 <config_path>"
    exit 1
fi

CONFIG_PATH="$1"

if [ ! -f "$CONFIG_PATH" ]; then
    echo "Error: Config file not found: $CONFIG_PATH"
    exit 1
fi

# Create backup directory if it doesn't exist
BACKUP_DIR="$(dirname "$CONFIG_PATH")/backups"
mkdir -p "$BACKUP_DIR"

# Create timestamped backup
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_PATH="$BACKUP_DIR/config.json.bak.$TIMESTAMP"

cp "$CONFIG_PATH" "$BACKUP_PATH"
echo "✓ Backup created: $BACKUP_PATH"