import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from auth_helper import get_bearer_token

# --- CONFIGURATION ---
MANAGEMENT_SERVER = "http://khangserver:9191"

# FLAG: Set to True to enable ALL groups (except blacklisted ones), False to use whitelist.txt
ENABLE_ALL = False 

# Filenames for your external lists
WHITELIST_FILE = "whitelist.txt"
BLACKLIST_FILE = "blacklist.txt"

def load_list_from_file(file_path):
    """Reads a text file line by line, cleans up whitespace, and ignores comments."""
    if not os.path.exists(file_path):
        print(f"⚠️ Warning: File '{file_path}' not found. Proceeding with an empty list.")
        return []
    
    parsed_lines = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            clean_line = line.strip()
            if clean_line and not clean_line.startswith("#"):
                parsed_lines.append(clean_line)
    return parsed_lines

def get_robust_session():
    """Creates a requests session configured to handle flaky/heavy connections."""
    session = requests.Session()
    
    # Configure auto-retries for connection drops and heavy server loads
    retries = Retry(
        total=5,                # Retry up to 5 times
        backoff_factor=1,       # Wait 1s, 2s, 4s... between retries
        status_forcelist=[500, 502, 503, 504], # Retry on server hiccups
        raise_on_status=False
    )
    
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def bulk_update_group_filtering():
    token = get_bearer_token()
    if not token:
        print("Authentication failed. Exiting.")
        return

    target_groups = load_list_from_file(WHITELIST_FILE)
    blacklist_groups = load_list_from_file(BLACKLIST_FILE)

    print(f"Loaded {len(target_groups)} keywords from {WHITELIST_FILE}")
    print(f"Loaded {len(blacklist_groups)} keywords from {BLACKLIST_FILE}")

    # Use our robust session instead of bare requests calls
    session = get_robust_session()
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept-Encoding": "gzip, deflate"  # Encourages server to compress the massive 14MB response
    }
    session.headers.update(headers)

    # 1. Fetch Master Group List
    print("Fetching master group list...")
    try:
        groups_resp = session.get(f"{MANAGEMENT_SERVER}/api/channels/groups/")
        if groups_resp.status_code != 200:
            print(f"Failed to fetch groups: {groups_resp.status_code}")
            return
        id_to_name_lookup = {g['id']: g['name'] for g in groups_resp.json() if 'id' in g and 'name' in g}
    except Exception as e:
        print(f"❌ Network error while fetching master group list: {e}")
        return

    # 2. Fetch all M3U accounts (The crash point)
    print("Fetching existing M3U accounts (This is a large payload, downloading...)...")
    try:
        # Added stream=False explicitly to ensure it loads cleanly if compression is used
        accounts_resp = session.get(f"{MANAGEMENT_SERVER}/api/m3u/accounts/", stream=False)
        if accounts_resp.status_code != 200:
            print(f"Failed to fetch accounts: {accounts_resp.status_code}")
            return
        data = accounts_resp.json()
    except requests.exceptions.ChunkedEncodingError as e:
        print(f"❌ Server cut the connection mid-transfer due to size. Error: {e}")
        print("Tip: If this keeps happening, your server might need its timeout settings increased.")
        return
    except Exception as e:
        print(f"❌ Failed to fetch accounts due to a network error: {e}")
        return
    
    accounts_list = [v for k, v in data.items() if k.isdigit()] if isinstance(data, dict) else data
    print(f"Found {len(accounts_list)} accounts to update. (Enable All Override: {ENABLE_ALL})")

    for account in accounts_list:
        acc_id = account.get('id')
        acc_name = account.get('name')
        print(f"\nProcessing Account: {acc_name} (ID: {acc_id})")

        # 3. Get detailed info for this specific account
        try:
            acc_detail = session.get(f"{MANAGEMENT_SERVER}/api/m3u/accounts/{acc_id}/").json()
        except Exception as e:
            print(f"  - ⚠️ Failed to fetch details for {acc_name}: {e}")
            continue
            
        available_groups = acc_detail.get('channel_groups', [])
        if not available_groups:
            print(f"  - No groups found for this account.")
            continue

        # 4. Construct the group_settings payload
        update_payload = []
        for g in available_groups:
            current_group_id = g['channel_group']
            current_group_name = id_to_name_lookup.get(current_group_id, "")
            group_name_lower = current_group_name.lower()
            
            is_blacklisted = any(bad_word.lower() in group_name_lower for bad_word in blacklist_groups)
            
            if is_blacklisted:
                is_enabled = False
            elif ENABLE_ALL:
                is_enabled = True
            else:
                is_enabled = any(target.lower() in group_name_lower for target in target_groups)
            
            update_payload.append({
                "channel_group": current_group_id,
                "enabled": is_enabled
            })

        # 5. Apply the update via PATCH
        print(f"  - Sending update for {len(update_payload)} groups...")
        patch_url = f"{MANAGEMENT_SERVER}/api/m3u/accounts/{acc_id}/group-settings/"
        try:
            patch_resp = session.patch(patch_url, json={"group_settings": update_payload})
            
            if patch_resp.status_code in [200, 204]:
                print(f"  - Successfully updated group filtering for {acc_name}.")
                
                # 6. Trigger the playlist refresh
                print(f"  - Triggering server refresh for {acc_name}...")
                refresh_url = f"{MANAGEMENT_SERVER}/api/m3u/refresh/{acc_id}/"
                refresh_resp = session.post(refresh_url)
                
                if refresh_resp.status_code in [200, 201, 202, 204]:
                    print(f"  - Successfully refreshed playlist for {acc_name}.")
                else:
                    print(f"  - Failed to refresh playlist for {acc_name}: {refresh_resp.status_code}")
            else:
                print(f"  - Failed to update {acc_name}: {patch_resp.status_code}")
        except Exception as e:
            print(f"  - ⚠️ Network error while updating or refreshing {acc_name}: {e}")

if __name__ == "__main__":
    bulk_update_group_filtering()