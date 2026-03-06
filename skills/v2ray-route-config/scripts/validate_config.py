#!/usr/bin/env python3
"""
Validate V2Ray configuration JSON structure
"""
import json
import sys

def validate_v2ray_config(config_path):
    """Validate V2Ray config.json file"""
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Check basic structure
        if 'routing' not in config:
            print(f"Error: 'routing' section not found in {config_path}")
            return False
            
        if 'rules' not in config['routing']:
            print(f"Error: 'routing.rules' section not found in {config_path}")
            return False
            
        # Validate each rule
        for i, rule in enumerate(config['routing']['rules']):
            if 'type' not in rule:
                print(f"Error: Rule {i} missing 'type' field")
                return False
            if 'outboundTag' not in rule:
                print(f"Error: Rule {i} missing 'outboundTag' field")
                return False
                
        print(f"✓ V2Ray config validated successfully: {config_path}")
        return True
        
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {config_path}: {e}")
        return False
    except FileNotFoundError:
        print(f"Error: Config file not found: {config_path}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 validate_config.py <config_path>")
        sys.exit(1)
        
    config_path = sys.argv[1]
    if validate_v2ray_config(config_path):
        sys.exit(0)
    else:
        sys.exit(1)