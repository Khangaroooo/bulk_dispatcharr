import os
import time
import requests
from auth_helper import get_bearer_token
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

# --- CONFIGURATION ---
MANAGEMENT_SERVER = "http://khangserver:9191"

# FLAG: Set to True to enable ALL non-blacklisted groups, False to ONLY enable whitelisted groups
ENABLE_ALL = False

# FLAG: Set to True to only process accounts with status == "error"
ONLY_ERRORS = True

# Delay in seconds between processing accounts
DELAY_SECONDS = 10

# Filenames for external lists
WHITELIST_FILE = "whitelist.txt"
BLACKLIST_FILE = "blacklist.txt"


def load_list_from_file(file_path):
  """Reads a text file line by line, cleans up whitespace, and ignores comments."""
  if not os.path.exists(file_path):
    print(
        f"⚠️ Warning: File '{file_path}' not found. Proceeding with an empty"
        " list."
    )
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
  retries = Retry(
      total=5,
      backoff_factor=1,
      status_forcelist=[500, 502, 503, 504],
      raise_on_status=False,
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

  session = get_robust_session()
  headers = {
      "Authorization": f"Bearer {token}",
      "Content-Type": "application/json",
      "Accept-Encoding": "gzip, deflate",
  }
  session.headers.update(headers)

  # 1. Fetch Master Group List
  print("Fetching master group list...")
  id_to_name_lookup = {}
  try:
    groups_resp = session.get(f"{MANAGEMENT_SERVER}/api/channels/groups/")
    if groups_resp.status_code == 200:
      groups_list = groups_resp.json()
      for g in groups_list:
        if "id" in g and "name" in g:
          id_to_name_lookup[str(g["id"])] = g["name"]
      print(
          f"Master group lookup ready with {len(id_to_name_lookup)} total"
          " groups."
      )
    else:
      print(f"Failed to fetch groups: {groups_resp.status_code}")
      return
  except Exception as e:
    print(f"❌ Network error while fetching master group list: {e}")
    return

  # 2. Fetch all M3U accounts
  print("Fetching existing M3U accounts...")
  try:
    accounts_resp = session.get(
        f"{MANAGEMENT_SERVER}/api/m3u/accounts/", stream=False
    )
    if accounts_resp.status_code != 200:
      print(f"Failed to fetch accounts: {accounts_resp.status_code}")
      return
    accounts_list = accounts_resp.json()
  except Exception as e:
    print(f"❌ Failed to fetch accounts: {e}")
    return

  print(
      f"Found {len(accounts_list)} total accounts. (Only Errors Mode:"
      f" {ONLY_ERRORS})"
  )

  for i, account in enumerate(accounts_list):
    acc_id = account.get("id")
    acc_name = account.get("name")
    acc_status = str(account.get("status", "")).lower()

    if ONLY_ERRORS and acc_status != "error":
      print(
          f"\nSkipping Account: {acc_name} (ID: {acc_id}) — Status:"
          f" '{acc_status}'"
      )
      continue

    print(
        f"\nProcessing Account: {acc_name} (ID: {acc_id}) — Status:"
        f" '{acc_status}'"
    )

    # 3. Fetch specific account details
    try:
      acc_detail = session.get(
          f"{MANAGEMENT_SERVER}/api/m3u/accounts/{acc_id}/"
      ).json()
    except Exception as e:
      print(f"  - ⚠️ Failed to fetch details for {acc_name}: {e}")
      continue

    available_groups = acc_detail.get("channel_groups", [])

    if not available_groups:
      print("  - No groups found for this account.")
      continue

    # 4. Construct update payload
    update_payload = []
    unresolved_ids = []

    for g in available_groups:
      group_id = g.get("channel_group")
      if group_id is None:
        continue

      group_id_str = str(group_id)
      group_name = id_to_name_lookup.get(group_id_str, "")

      if not group_name:
        unresolved_ids.append(group_id_str)

      group_name_lower = group_name.lower()

      is_whitelisted = (
          any(target.lower() in group_name_lower for target in target_groups)
          if group_name
          else False
      )
      is_blacklisted = (
          any(bad_word.lower() in group_name_lower for bad_word in blacklist_groups)
          if group_name
          else False
      )

      # Decision logic: Whitelist ALWAYS takes precedence
      if is_whitelisted:
        is_enabled = True
      elif is_blacklisted:
        is_enabled = False
      else:
        is_enabled = ENABLE_ALL

      update_payload.append(
          {"channel_group": group_id, "enabled": is_enabled}
      )

    if unresolved_ids:
      print(
          f"  - ⚠️ Could not resolve names for {len(unresolved_ids)} group"
          f" IDs (e.g. {unresolved_ids[:5]})."
      )

    # 5. Send PATCH update
    print(f"  - Sending update for {len(update_payload)} groups...")
    patch_url = (
        f"{MANAGEMENT_SERVER}/api/m3u/accounts/{acc_id}/group-settings/"
    )
    try:
      patch_resp = session.patch(
          patch_url, json={"group_settings": update_payload}
      )

      if patch_resp.status_code in [200, 204]:
        print(f"  - Successfully updated group filtering for {acc_name}.")

        # 6. Trigger server refresh
        print(f"  - Triggering server refresh for {acc_name}...")
        refresh_url = f"{MANAGEMENT_SERVER}/api/m3u/refresh/{acc_id}/"
        refresh_resp = session.post(refresh_url)

        if refresh_resp.status_code in [200, 201, 202, 204]:
          print(f"  - Successfully refreshed playlist for {acc_name}.")
        else:
          print(
              "  - Failed to refresh playlist for"
              f" {acc_name}: {refresh_resp.status_code}"
          )
      else:
        print(f"  - Failed to update {acc_name}: {patch_resp.status_code}")
    except Exception as e:
      print(
          f"  - ⚠️ Network error while updating or refreshing {acc_name}: {e}"
      )

    # 7. Delay before processing next account
    if DELAY_SECONDS > 0 and i < len(accounts_list) - 1:
      print(
          f"  - ⏳ Waiting {DELAY_SECONDS} seconds before processing the next"
          " account..."
      )
      time.sleep(DELAY_SECONDS)


if __name__ == "__main__":
  bulk_update_group_filtering()