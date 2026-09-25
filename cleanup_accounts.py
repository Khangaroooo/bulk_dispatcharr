import requests
from auth_helper import get_bearer_token

# --- CONFIGURATION ---
MANAGEMENT_SERVER = "http://khangserver:9191"
PAGE_SIZE = 100  # Request larger chunks from the server to reduce API hits


def fetch_all_paginated_data(endpoint_url, headers):
    """Helper function to auto-fetch all items across multiple pages if paginated."""
    all_items = []
    current_url = endpoint_url

    # If the URL doesn't have query params yet, start with our larger limit
    if "?" not in current_url:
        # Trying common pagination overrides: 'limit' or 'page_size'
        current_url = f"{endpoint_url}?limit={PAGE_SIZE}&page_size={PAGE_SIZE}"

    while current_url:
        try:
            resp = requests.get(current_url, headers=headers)
            if resp.status_code != 200:
                print(
                    f"Error fetching data from {current_url}: Code {resp.status_code}"
                )
                break

            data = resp.json()

            # Handle standard list responses
            if isinstance(data, list):
                all_items.extend(data)
                break  # Standard lists aren't paginated via next links

            # Handle standard dict responses
            elif isinstance(data, dict):
                # Case A: Standard DRF/Offset-limit pagination dict structure
                # {"count": X, "next": "URL", "previous": null, "results": [...]}
                if "results" in data and isinstance(data["results"], list):
                    all_items.extend(data["results"])
                    current_url = data.get("next")  # Move to next page URL

                # Case B: Your original EPG dictionary format (ID keys mapping to objects)
                else:
                    # Filter out non-digit keys if any, otherwise grab all values
                    items_list = [
                        v for k, v in data.items() if str(k).isdigit()
                    ]
                    if items_list:
                        all_items.extend(items_list)
                    else:
                        # If it's a single object dict or a different format, append it
                        all_items.append(data)
                    break
            else:
                break
        except Exception as e:
            print(f"Exception during fetch: {e}")
            break

    return all_items


def cleanup_failed_accounts():
    token = get_bearer_token()
    if not token:
        print("Authentication failed. Exiting.")
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # 1. Fetch all M3U accounts (Auto-handling pagination)
    print("Fetching all M3U accounts...")
    accounts_list = fetch_all_paginated_data(
        f"{MANAGEMENT_SERVER}/api/m3u/accounts/", headers
    )
    print(f"Total M3U accounts fetched: {len(accounts_list)}")

    # 2. Fetch all EPG sources (Auto-handling pagination)
    print("Fetching all EPG sources...")
    epg_list = fetch_all_paginated_data(
        f"{MANAGEMENT_SERVER}/api/epg/sources/", headers
    )
    print(f"Total EPG sources fetched: {len(epg_list)}")

    # --- 3. Clean up Errored M3U Accounts ---
    print(f"\nScanning {len(accounts_list)} M3U accounts for errors...")
    for account in accounts_list:
        acc_id = account.get("id")
        acc_name = account.get("name")
        status = account.get("status", "").lower()

        if status == "error":
            print(
                f"[!] M3U Cleanup Triggered: {acc_name} (ID: {acc_id}) | Status: {status}"
            )
            m3u_del_resp = requests.delete(
                f"{MANAGEMENT_SERVER}/api/m3u/accounts/{acc_id}/",
                headers=headers,
            )

            if m3u_del_resp.status_code in [200, 204]:
                print(f"  - Success: M3U {acc_name} removed.")
            else:
                print(
                    f"  - Error: Could not remove M3U (Code: {m3u_del_resp.status_code})"
                )

    # --- 4. Clean up Errored EPG Sources ---
    print(f"\nScanning {len(epg_list)} EPG sources for errors...")
    for epg in epg_list:
        epg_id = epg.get("id")
        epg_name = epg.get("name")
        epg_status = epg.get("status", "").lower()

        if epg_status == "error":
            print(
                f"[!] EPG Cleanup Triggered: {epg_name} (ID: {epg_id}) | Status: {epg_status}"
            )
            epg_del_resp = requests.delete(
                f"{MANAGEMENT_SERVER}/api/epg/sources/{epg_id}/",
                headers=headers,
            )

            if epg_del_resp.status_code in [200, 204]:
                print(f"  - Success: EPG {epg_name} removed.")
            else:
                print(
                    f"  - Error: Could not remove EPG (Code: {epg_del_resp.status_code})"
                )

    print("\nScan and cleanup finished.")


if __name__ == "__main__":
    cleanup_failed_accounts()