import requests
from auth_helper import get_bearer_token

# --- CONFIGURATION ---
MANAGEMENT_SERVER = "http://khangserver:9191"

# FLAG: Set to True to enable ALL groups, False to use the TARGET_GROUPS list
ENABLE_ALL = True 

TARGET_GROUPS = [
    "Main Events / PPV", "US - Entertainment", "US - Movies", 
    "US - Sports", "FanDuel Sports", "SuperSports", 
    "NHL", "NHL.2", "Canada", "DAZN", "PARAMOUNT", "PPV", 
    "SPORTS EXCLUSIVE", "USA SPORTS", "Default Group", "4K", 
    "DISCOVERY +", "HBO MAX", "PEACOCK", "ESPN"
]

def bulk_update_group_filtering():
    token = get_bearer_token()
    if not token:
        print("Authentication failed. Exiting.")
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # 1. Fetch Master Group List to map names to IDs
    print("Fetching master group list...")
    groups_resp = requests.get(f"{MANAGEMENT_SERVER}/api/channels/groups/", headers=headers)
    if groups_resp.status_code != 200:
        print(f"Failed to fetch groups: {groups_resp.status_code}")
        return
    
    group_lookup = {g['name']: g['id'] for g in groups_resp.json() if 'name' in g}

    # 2. Fetch all M3U accounts
    print("Fetching existing M3U accounts...")
    accounts_resp = requests.get(f"{MANAGEMENT_SERVER}/api/m3u/accounts/", headers=headers)
    if accounts_resp.status_code != 200:
        print(f"Failed to fetch accounts: {accounts_resp.status_code}")
        return
    
    data = accounts_resp.json()
    accounts_list = [v for k, v in data.items() if k.isdigit()] if isinstance(data, dict) else data

    print(f"Found {len(accounts_list)} accounts to update. (Enable All: {ENABLE_ALL})")

    for account in accounts_list:
        acc_id = account.get('id')
        acc_name = account.get('name')
        print(f"\nProcessing Account: {acc_name} (ID: {acc_id})")

        # 3. Get detailed info for this specific account
        acc_detail = requests.get(f"{MANAGEMENT_SERVER}/api/m3u/accounts/{acc_id}/", headers=headers).json()
        available_groups = acc_detail.get('channel_groups', [])
        
        if not available_groups:
            print(f"  - No groups found for this account.")
            continue

        # 4. Construct the group_settings payload
        update_payload = []
        for g in available_groups:
            current_group_id = g['channel_group']
            
            # Logic for the Flag
            if ENABLE_ALL:
                is_enabled = True
            else:
                is_enabled = any(group_lookup.get(target_name) == current_group_id for target_name in TARGET_GROUPS)
            
            update_payload.append({
                "channel_group": current_group_id,
                "enabled": is_enabled
            })

        # 5. Apply the update via PATCH
        print(f"  - Sending update for {len(update_payload)} groups...")
        patch_url = f"{MANAGEMENT_SERVER}/api/m3u/accounts/{acc_id}/group-settings/"
        patch_resp = requests.patch(patch_url, headers=headers, json={"group_settings": update_payload})
        
        if patch_resp.status_code in [200, 204]:
            print(f"  - Successfully updated group filtering for {acc_name}.")
        else:
            print(f"  - Failed to update {acc_name}: {patch_resp.status_code}")

if __name__ == "__main__":
    bulk_update_group_filtering()