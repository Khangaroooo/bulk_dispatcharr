import requests
import json
import os
import uuid
from urllib.parse import urlparse, parse_qs
from auth_helper import get_bearer_token

# --- CONFIGURATION ---
# Set to True to enable every group found on the account
# Set to False to only enable groups listed in TARGET_GROUPS
ENABLE_ALL = True 

TARGET_GROUPS = [
    "Main Events / PPV", "US - Entertainment", "US - Movies", 
    "US - Sports", "FanDuel Sports", "SuperSports", 
    "NHL", "NHL.2", "Canada", "DAZN", "PARAMOUNT", "PPV", 
    "SPORTS EXCLUSIVE", "USA SPORTS", "Default Group", "4K", 
    "DISCOVERY +", "HBO MAX", "PEACOCK", "ESPN"
]

def run_iptv_replication(mgmt_url, token, iptv_url):
    parsed_url = urlparse(iptv_url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    params = parse_qs(parsed_url.query)
    
    username = params.get('username', [None])[0]
    password = params.get('password', [None])[0]

    unique_id = str(uuid.uuid4())[:8]
    account_name = f"IPTV_{unique_id}"

    if not username or not password:
        print("  - Error: URL missing credentials.")
        return

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # 1. Create the M3U Account
    create_payload = {
        "name": account_name,
        "server_url": base_url,
        "user_agent": None,
        "is_active": True,
        "max_streams": 1,
        "refresh_interval": 24,
        "account_type": "XC",
        "username": username,
        "password": password,
        "stale_stream_days": 7,
        "priority": 0,
        "enable_vod": False
    }

    print(f"  - Creating account: {account_name}...")
    create_resp = requests.post(f"{mgmt_url}/api/m3u/accounts/", headers=headers, json=create_payload)
    
    if create_resp.status_code not in [200, 201]:
        print(f"  - Failed to create account: {create_resp.status_code}")
        return

    account_id = create_resp.json().get('id')
    print(f"  - Account Created. ID: {account_id}")

    # 2. Configure Auto-Enable Settings
    settings_payload = {
        "auto_enable_new_groups_live": True,
        "auto_enable_new_groups_vod": True,
        "auto_enable_new_groups_series": True
    }
    requests.patch(f"{mgmt_url}/api/m3u/accounts/{account_id}/", headers=headers, json=settings_payload)

    # 3. Apply Group Filtering Logic
    print("  - Fetching group lists and mapping IDs...")
    all_groups_resp = requests.get(f"{mgmt_url}/api/channels/groups/", headers=headers).json()
    group_lookup = {g['name']: g['id'] for g in all_groups_resp if 'name' in g}

    acc_info = requests.get(f"{mgmt_url}/api/m3u/accounts/{account_id}/", headers=headers).json()
    available_groups = acc_info.get('channel_groups', [])
    
    group_settings = []
    for g in available_groups:
        current_id = g['channel_group']
        
        # New Flag Logic: If ENABLE_ALL is true, every group is enabled.
        # Otherwise, check against the TARGET_GROUPS list.
        if ENABLE_ALL:
            is_enabled = True
        else:
            # Check against the TARGET_GROUPS list
            is_enabled = any(group_lookup.get(target_name) == current_id for target_name in TARGET_GROUPS)
        
        group_settings.append({
            "channel_group": current_id,
            "enabled": is_enabled
        })

    if group_settings:
        print(f"  - Updating group selections (Enable All: {ENABLE_ALL})...")
        requests.patch(
            f"{mgmt_url}/api/m3u/accounts/{account_id}/group-settings/", 
            headers=headers, 
            json={"group_settings": group_settings}
        )

    # 4. Create EPG Source
    epg_url = f"{base_url}/xmltv.php?username={username}&password={password}"
    epg_payload = {
        "name": f"{account_name}_EPG",
        "source_type": "xmltv",
        "url": epg_url,
        "is_active": True,
        "refresh_interval": 24
    }
    print(f"  - Registering EPG source: {epg_payload['name']}...")
    requests.post(f"{mgmt_url}/api/epg/sources/", headers=headers, json=epg_payload)

    # 5. Trigger Account Refresh
    print(f"  - Refreshing account {account_id}...")
    refresh_resp = requests.post(f"{mgmt_url}/api/m3u/refresh/{account_id}/", headers=headers)
    if refresh_resp.status_code == 202:
        print(f"  - Flow Replicated Successfully for {account_name}.")
    else:
        print(f"  - Refresh failed: {refresh_resp.text}")

if __name__ == "__main__":
    print("Authenticating with management server...")
    current_token = get_bearer_token()
    # Ensure management server URL is pulled from environment or defined
    base_mgmt_url = os.getenv("BASE_URL") or "http://khangserver:9191"

    if not current_token:
        print("Critical Error: Could not retrieve authentication token. Exiting.")
    else:
        file_path = "url.txt"
        if not os.path.exists(file_path):
            print(f"Error: {file_path} not found.")
        else:
            with open(file_path, "r") as f:
                urls = [line.strip() for line in f if line.strip()]
            
            print(f"Found {len(urls)} URLs to process. Global Enable All: {ENABLE_ALL}")
            
            for index, url in enumerate(urls, start=1):
                print(f"\n--- Processing URL {index}/{len(urls)} ---")
                try:
                    run_iptv_replication(base_mgmt_url, current_token, url)
                except Exception as e:
                    print(f"  - Failed to process URL: {e}")
            
            print("\nAll tasks completed.")