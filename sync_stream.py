import requests
import urllib.parse
import os
import re
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
    
    channels_list = []
    if isinstance(data, list):
        channels_list = data
    elif isinstance(data, dict):
        if "results" in data:
            channels_list = data["results"]
        elif any(k.isdigit() for k in data.keys()):
            channels_list = [v for k, v in data.items() if k.isdigit()]
        else:
            print("Unknown dictionary structure. Keys found:", data.keys())
            return

    print(f"Found {len(channels_list)} channels to process.")

    for channel in channels_list:
        channel_id = channel.get('id')
        channel_name = channel.get('name', '')
        
        # Clean basic whitespace/newlines
        clean_name = channel_name.replace('\n', '').replace('\r', '').strip()
        existing_ids = [s['id'] for s in channel.get('streams', [])]
        
        # 1. Parse out the Region prefix if it exists
        region_match = re.match(r"^([A-Za-z0-9]{2,4})\s*[:|]\s*(.*)$", clean_name)
        
        if region_match:
            region = region_match.group(1)
            base_name = region_match.group(2).strip()
        else:
            region = None
            base_name = clean_name

        # 2. Strip out any existing quality flags to get a completely raw name
        pure_base_name = re.sub(r'\b(4K|FHD|HD)\b', '', base_name, flags=re.I)
        pure_base_name = re.sub(r'\s+', ' ', pure_base_name).strip() # Clean dangling spaces
        
        print(f"Processing '{clean_name}' (ID: {channel_id}) -> Core Base: '{pure_base_name}'" + (f" [{region}]" if region else ""))

        # 3. Search sequentially following your quality tier hierarchy
        qualities = ["4K", "FHD", "HD", ""]
        found_ids = []
        
        for q in qualities:
            # Build the core name for this specific tier
            stream_core = f"{pure_base_name} {q}".strip() if q else pure_base_name
            
            # Combine the tier name with your regional prefix variations
            if region:
                q_terms = [
                    f"{region}: {stream_core}",
                    f"{region} | {stream_core}",
                    f"{region}| {stream_core}",
                    f"{region}|{stream_core}"
                ]
            else:
                q_terms = [stream_core]
                
            q_terms = list(dict.fromkeys(q_terms))
            
            # Execute searches for this quality tier
            for term in q_terms:
                encoded_name = urllib.parse.quote(term)
                search_url = f"{base_url}/api/channels/streams/ids/?name={encoded_name}"
                search_res = requests.get(search_url, headers=HEADERS)
                
                if search_res.status_code == 200:
                    res_ids = search_res.json()
                    if isinstance(res_ids, list):
                        found_ids.extend(res_ids)

        # 4. Deduplicate found IDs while preserving their strict high-to-low quality order
        prioritized_ids = list(dict.fromkeys(found_ids))
        
        # Append any pre-existing stream IDs that the search missed so nothing gets lost
        final_ids = prioritized_ids + [x for x in existing_ids if x not in prioritized_ids]
        
        # 5. Patch if there are new streams OR if the quality sorting sequence changed
        if final_ids != existing_ids:
            patch_url = f"{base_url}/api/channels/channels/{channel_id}/"
            payload = {"id": channel_id, "streams": final_ids}
            patch_res = requests.patch(patch_url, json=payload, headers=HEADERS)
            
            if patch_res.status_code in [200, 204]:
                print(f"  - Successfully synced {len(final_ids)} streams in quality priority order.")
            else:
                print(f"  - Patch failed: {patch_res.status_code}")
        else:
            print("  - Streams are already matched and properly sorted by quality.")

if __name__ == "__main__":
    sync_channels()