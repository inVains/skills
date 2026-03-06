#!/usr/bin/env python3
"""
Add direct routing rule for specific domains to V2Ray config
"""
import json
import sys
import copy

def add_direct_rule(config_path, domains):
    """Add direct routing rule for given domains"""
    try:
        # Read current config
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Create new rule
        new_rule = {
            "type": "field",
            "domain": domains if isinstance(domains, list) else [domains],
            "outboundTag": "direct"
        }
        
        # Add rule to beginning of routing rules (high priority)
        if 'routing' not in config:
            config['routing'] = {'rules': []}
        if 'rules' not in config['routing']:
            config['routing']['rules'] = []
            
        # Insert at position 1 (after any private network rules, before general rules)
        config['routing']['rules'].insert(1, new_rule)
        
        # Write back to file
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
            
        print(f"✓ Added direct rule for domains: {domains}")
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 add_direct_rule.py <config_path> <domain1> [domain2] ...")
        sys.exit(1)
        
    config_path = sys.argv[1]
    domains = sys.argv[2:]
    
    if add_direct_rule(config_path, domains):
        sys.exit(0)
    else:
        sys.exit(1)