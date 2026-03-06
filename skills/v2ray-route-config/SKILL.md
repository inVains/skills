---
name: v2ray-route-config
description: Manage and modify V2Ray routing configurations safely. Use when needing to add, remove, or modify routing rules in V2Ray config.json files, especially for domain-based routing (e.g., adding direct/bypass rules for specific domains like coding.dashscope.aliyuncs.com). Handles common V2Ray config locations and validates JSON structure before applying changes.
---

# V2Ray Route Config

## Overview

This skill provides safe, structured management of V2Ray routing configurations. It handles the complexity of JSON manipulation while ensuring configuration integrity through validation and backup.

## When to Use

- Adding direct/bypass rules for specific domains
- Modifying existing routing rules
- Validating V2Ray configuration structure
- Working with common V2Ray config locations (`/etc/v2ray/config.json`, `/usr/local/etc/v2ray/config.json`)

## Workflow

### 1. Locate Configuration
Check common V2Ray config paths:
- `/etc/v2ray/config.json`
- `/usr/local/etc/v2ray/config.json`
- `~/.config/v2ray/config.json`

### 2. Backup Current Config
Always create a timestamped backup before modifications:
```bash
cp config.json config.json.bak.$(date +%Y%m%d_%H%M%S)
```

### 3. Validate JSON Structure
Ensure the config is valid JSON before making changes.

### 4. Apply Routing Changes
Modify the `routing.rules` array to add/remove routing rules.

### 5. Validate Modified Config
Verify the updated config is still valid JSON.

### 6. Restart V2Ray Service
Apply changes by restarting the V2Ray service.

## Resources

### scripts/
- `add_direct_rule.py` - Add direct routing rule for specific domains
- `validate_config.py` - Validate V2Ray config JSON structure
- `backup_config.sh` - Create timestamped backup of config file

### references/
- `v2ray_routing_schema.md` - V2Ray routing configuration schema reference
- `common_rules.md` - Examples of common routing rules and patterns