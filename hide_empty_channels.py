import requests
from auth_helper import get_bearer_token

# --- CONFIGURATION ---
MANAGEMENT_SERVER = "http://khangserver:9191"
PROFILE_ID = 2

def sync_channel_visibility():
    token = get_bearer_token()
    if not token:
        print("Authentication failed. Exiting.")
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    url = f"{MANAGEMENT_SERVER}/api/channels/channels/"
    print("Fetching channels and updating visibility profiles...")

    while url:
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            print(f"Failed to fetch channels: {resp.status_code}")
            return
        
        data = resp.json()

        # Safely handle both paginated dicts and flat lists
        if isinstance(data, dict):
            channels_list = data.get('results', [])
            url = data.get('next')  # Advance to next page if it exists
        elif isinstance(data, list):
            channels_list = data
            url = None  # Flat list means no pagination metadata, break the loop after this
        else:
            print(f"Unexpected data format received: {type(data)}")
            return

        print(f"Processing {len(channels_list)} channels...")

        for channel in channels_list:
            channel_id = channel.get('id')
            channel_name = channel.get('name')
            streams = channel.get('streams', [])

            # Determine state: Enabled if streams list is NOT empty
            is_enabled = len(streams) > 0
            action_text = "Enabling" if is_enabled else "Hiding (Empty Streams)"

            patch_url = f"{MANAGEMENT_SERVER}/api/channels/profiles/{PROFILE_ID}/channels/{channel_id}/"
            payload = {"enabled": is_enabled}

            patch_resp = requests.patch(patch_url, json=payload, headers=headers)

            if patch_resp.status_code in [200, 204]:
                print(f"  - Success: {action_text} -> {channel_name} (ID: {channel_id})")
            else:
                print(f"  - Error: Could not update profile for {channel_name} (Code: {patch_resp.status_code})")

    print("\nChannel visibility sync finished.")

if __name__ == "__main__":
    sync_channel_visibility()