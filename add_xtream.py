import os
import uuid
from urllib.parse import urlparse, parse_qs
from auth_helper import get_bearer_token

# Import our shared logic engine
from iptv_utils import (
    get_robust_session, 
    load_list_from_file, 
    is_group_enabled, 
    WHITELIST_FILE, 
    BLACKLIST_FILE
)

# --- CONFIGURATION ---
# Set to True to enable every group found on the account (except blacklisted items)
# Set to False to respect your whitelist.txt entries
ENABLE_ALL = True 

# Maximum number of URLs permitted per individual domain/host
MAX_URLS_PER_HOST = 50

def run_iptv_replication(session, mgmt_url, iptv_url, whitelist, blacklist):
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
    create_resp = session.post(f"{mgmt_url}/api/m3u/accounts/", json=create_payload)
    
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
    session.patch(f"{mgmt_url}/api/m3u/accounts/{account_id}/", json=settings_payload)

    # 3. Apply Centralized Group Filtering Logic
    print("  - Fetching group lists and mapping IDs...")
    all_groups_resp = session.get(f"{mgmt_url}/api/channels/groups/").json()
    id_to_name_lookup = {g['id']: g['name'] for g in all_groups_resp if 'id' in g and 'name' in g}

    acc_info = session.get(f"{mgmt_url}/api/m3u/accounts/{account_id}/").json()
    available_groups = acc_info.get('channel_groups', [])
    
    group_settings = []
    for g in available_groups:
        current_id = g['channel_group']
        current_name = id_to_name_lookup.get(current_id, "")
        
        # Evaluate group visibility using unified utility rules
        is_enabled = is_group_enabled(current_name, whitelist, blacklist, ENABLE_ALL)
        
        group_settings.append({
            "channel_group": current_id,
            "enabled": is_enabled
        })

    if group_settings:
        print(f"  - Updating group selections (Enable All Override: {ENABLE_ALL})...")
        session.patch(
            f"{mgmt_url}/api/m3u/accounts/{account_id}/group-settings/", 
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
    session.post(f"{mgmt_url}/api/epg/sources/", json=epg_payload)

    # 5. Trigger Account Refresh
    print(f"  - Refreshing account {account_id}...")
    refresh_resp = session.post(f"{mgmt_url}/api/m3u/refresh/{account_id}/")
    if refresh_resp.status_code in [200, 201, 202, 204]:
        print(f"  - Flow Replicated Successfully for {account_name}.")
    else:
        print(f"  - Refresh failed: {refresh_resp.text}")

if __name__ == "__main__":
    print("Authenticating with management server...")
    current_token = get_bearer_token()
    base_mgmt_url = os.getenv("BASE_URL") or "http://khangserver:9191"

    if not current_token:
        print("Critical Error: Could not retrieve authentication token. Exiting.")
    else:
        # Load parsing rules once globally from the text documents
        whitelist = load_list_from_file(WHITELIST_FILE)
        blacklist = load_list_from_file(BLACKLIST_FILE)
        
        # Establish our unified, robust network session wrapper
        session = get_robust_session(current_token)
        
        file_path = "url.txt"
        if not os.path.exists(file_path):
            print(f"Error: {file_path} not found.")
        else:
            with open(file_path, "r") as f:
                urls = [line.strip() for line in f if line.strip()]
            
            print(f"Found {len(urls)} total URLs in file. Global Enable All: {ENABLE_ALL}")
            
            # Tracker dictionary to count how many URLs we've processed per unique domain
            host_counts = {}
            
            for index, url in enumerate(urls, start=1):
                print(f"\n--- Processing URL {index}/{len(urls)} ---")
                try:
                    # Parse out the host/domain name (e.g., 'providerdomain.com:8080')
                    parsed_url = urlparse(url)
                    host = parsed_url.netloc
                    
                    if not host:
                        print("  - Skipped: Invalid URL structure (could not parse domain).")
                        continue
                    
                    # Track host count incrementation
                    host_counts[host] = host_counts.get(host, 0) + 1
                    
                    # If this host has crossed our threshold constraint, ignore it
                    if host_counts[host] > MAX_URLS_PER_HOST:
                        print(f"  - Skipped: Host '{host}' has already processed {MAX_URLS_PER_HOST} accounts.")
                        continue
                    
                    # Pass the session and text lists through to execution loop
                    run_iptv_replication(session, base_mgmt_url, url, whitelist, blacklist)
                    
                except Exception as e:
                    print(f"  - Failed to process URL due to unexpected error: {e}")
            
            print("\nAll tasks completed.")