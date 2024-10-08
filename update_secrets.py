## Update ESPHome Secrets
# Updates the secrets.yaml file for esphome via Bitwarden
#
# This script assumes a few things:
#  - That you have the 'bw' command-line bitwarden binary in your path
#  - That you've already logged into Bitwarden via this binary
#  - That you've created a secure note item in Bitwarden and added at least one custom field to it.
#  - That you have requests and pytz installed and available in Python (via pip or OS)
#
# You can delete the extra custom field afterward, and I'll make modifications to support NOT having this later
#  nor having a note with a default name, but for right now, this is required. Set note_id below to the UUID for yours.
# Set the localtz to the appropriate name for your timezone.
#
# ## WARNING ##
# This is CURRENTLY a destructive script and WILL overwrite your local secrets.yaml file AND bitwarden entry without asking
# You have been warned!

import requests, yaml, subprocess, os, pytz, sys
from pathlib import Path
from datetime import datetime
from dateutil import parser
from socket import socket, AF_INET, SOCK_STREAM

bw_port = 42666
note_id = "220ddfa8-9820-49a9-b525-af2d0002b861"
localtz = 'US/Central'

api_url = f"http://localhost:{bw_port}"

def is_port_in_use(port: int) -> bool:
    try:
        with socket(AF_INET, SOCK_STREAM) as s:
            return s.connect_ex(('localhost', port)) == 0
    except:
        return True
def unlock_loop():
    try:
        r = requests.Response()
        while r.status_code != 200:
            bw_pass = ""
            while bw_pass == "":
                bw_pass = input("BW pass? ")
            r = requests.post(f"{api_url}/unlock",json={'password':bw_pass})
            if r.status_code != 200:
                message = r.json()['message']
                print(f"ERROR: {message}")
    except KeyboardInterrupt:
        print("Cancelling unlock")
        sys.exit(1)

if not is_port_in_use(bw_port):
    try:
        bw_server = subprocess.Popen(['bw','serve','--port',str(bw_port)])
    except FileNotFoundError:
        print("ERROR: 'bw' binary not found!")
        sys.exit(1)
    unlock_loop()
else:
    r = requests.get(api_url + '/status')
    response = r.json()['data']['template']
    if response['status'] == 'locked':
        unlock_loop()
    else:
        print("Bitwarden vault already unlocked; proceeding")
    r = requests.post(f"{api_url}/sync")
    
r = requests.get(f"{api_url}/object/item/{note_id}")
bw_note_info = r.json()['data']
bw_secrets = {x['name']:x['value'] for x in bw_note_info['fields']}

if not os.path.exists('secrets.yaml'):
    with open('secrets.yaml','w') as f:
        yaml.dump(bw_secrets,f,yaml.Dumper)
    print("No secrets file existed, created from Bitwarden")
    sys.exit(0)

with open('secrets.yaml') as f:
    file_secrets = yaml.load(f,yaml.FullLoader)

bw_secret_keys = bw_secrets.keys()
file_secret_keys = file_secrets.keys()
overlaps = [x for x in bw_secret_keys if x in file_secret_keys and file_secrets[x] != bw_secrets[x]]
if len(overlaps) > 0:
    print(f"Found {len(overlaps)} mismatched overlapped keys: {overlaps}")
else:
    print("No overlaps, can merge safely!")
file_mtime_raw = datetime.fromtimestamp(Path('secrets.yaml').stat().st_mtime)
central = pytz.timezone(localtz)
file_mtime = central.localize(file_mtime_raw)
bw_mtime = parser.isoparse(bw_note_info['revisionDate'])

all_secrets = {}
if bw_mtime > file_mtime:
    print("Bitwarden is newer, will overwrite changes from Bitwarden")
    for key in file_secret_keys:
        all_secrets[key] = file_secrets[key]
    for key in bw_secret_keys:
        all_secrets[key] = bw_secrets[key]
else:
    print("Local file is newer, will overwrite changes from local file")
    for key in bw_secret_keys:
        all_secrets[key] = bw_secrets[key]
    for key in file_secret_keys:
        all_secrets[key] = file_secrets[key]

key_count = len(all_secrets.keys())
bw_note_info['fields'] = [{"name":x, "value": all_secrets[x], "type": 1} for x in all_secrets.keys()]
r = requests.put(f"{api_url}/object/item/{note_id}",json=bw_note_info)
if r.status_code == 200 and r.json()['success'] == True:
    print(f"Successfully wrote {key_count} keys to Bitwarden, syncing...")
else:
    print(f"ERROR: {r.text}")
    sys.exit(1)
r = requests.post(f"{api_url}/sync")
if r.status_code == 200 and r.json()['success'] == True:
    print("Successfully synced changes!")
with open('secrets.yaml','w') as f:
    yaml.dump(all_secrets,f,yaml.Dumper)
    print(f"Wrote {key_count} keys to 'secrets.yaml'")
print("Finished!")