import requests
import urllib.parse
import os
from auth_helper import get_bearer_token

def sync_channels():
    base_url = os.getenv("BASE_URL")

    token = get_bearer_token()
    if not token:
        print("Could not authenticate. Exiting.")
        return
    
    HEADERS = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0"
    }

    print("Fetching channels...")
    get_url = f"{base_url}/api/channels/channels/?page=1&page_size=50&include_streams=true&show_disabled=true&ordering=channel_number"
    
    response = requests.get(get_url, headers=HEADERS)
    if response.status_code != 200:
        print(f"Error fetching channels: {response.status_code}")
        return

    data = response.json()
    
    # 1. Identify where the channel list actually lives
    channels_list = []
    
    if isinstance(data, list):
        channels_list = data
    elif isinstance(data, dict):
        # Check for standard 'results' key used in paginated APIs
        if "results" in data:
            channels_list = data["results"]
        # Check for your specific log format: {"0": {...}, "1": {...}}
        elif any(k.isdigit() for k in data.keys()):
            channels_list = [v for k, v in data.items() if k.isdigit()]
        else:
            # Fallback: if it's a dict and we don't recognize the keys, 
            # print it so we can see what's happening
            print("Unknown dictionary structure. Keys found:", data.keys())
            return

    print(f"Found {len(channels_list)} channels to process.")

    for channel in channels_list:
        channel_id = channel.get('id')
        channel_name = channel.get('name', '')
        
        # Clean the name: remove tags and newlines found in your text file
        import re
            
        # Use .strip() to clean up any weird whitespace/newlines seen in your log 
        clean_name = channel_name.replace('\n', '').replace('\r', '').strip()
        
        # Get existing stream IDs [cite: 4]
        existing_ids = [s['id'] for s in channel.get('streams', [])]
        
        print(f"Searching streams for: '{clean_name}' (ID: {channel_id})")

        # Search request [cite: 6]
        encoded_name = urllib.parse.quote(clean_name)
        search_url = f"{base_url}/api/channels/streams/ids/?name={encoded_name}"
        search_res = requests.get(search_url, headers=HEADERS)
        
        if search_res.status_code == 200:
            found_ids = search_res.json() # Expecting a list like [74556, 75047, ...] [cite: 7]
            
            # Deduplicate: combine existing and found [cite: 8]
            final_ids = list(set(existing_ids + found_ids))
            
            # Patch request [cite: 8]
            patch_url = f"{base_url}/api/channels/channels/{channel_id}/"
            payload = {"id": channel_id, "streams": final_ids}
            
            patch_res = requests.patch(patch_url, json=payload, headers=HEADERS)
            
            if patch_res.status_code in [200, 204]:
                print(f"  - Successfully synced {len(final_ids)} total streams.")
            else:
                print(f"  - Patch failed: {patch_res.status_code}")

if __name__ == "__main__":
    sync_channels()