# V2Ray Routing Configuration Schema

## Basic Structure

```json
{
  "routing": {
    "domainStrategy": "AsIs",
    "rules": [
      {
        "type": "field",
        "domain": ["domain1.com", "domain2.com"],
        "outboundTag": "direct"
      },
      {
        "type": "field",
        "ip": ["geoip:private"],
        "outboundTag": "direct"
      }
    ]
  }
}
```

## Rule Types

### Domain-based Rules
- `domain`: Array of domains to match
- Common outbound tags: `direct`, `proxy`, `block`

### IP-based Rules  
- `ip`: Array of IP ranges or geoip tags
- Examples: `["geoip:private"]`, `["geoip:cn"]`

## Common Patterns

### Direct/Bypass Rule
```json
{
  "type": "field",
  "domain": ["example.com"],
  "outboundTag": "direct"
}
```

### Proxy Rule
```json
{
  "type": "field", 
  "domain": ["google.com"],
  "outboundTag": "proxy"
}
```

### Block Rule
```json
{
  "type": "field",
  "domain": ["ads.com"],
  "outboundTag": "block" 
}
```

## Rule Order Priority

Rules are processed in order from top to bottom. First matching rule wins.

**Recommended order:**
1. Private/internal networks (direct)
2. Specific domains that should be direct (like coding.dashscope.aliyuncs.com)
3. GeoIP China rules (direct)
4. Proxy rules for international traffic
5. Default catch-all rule