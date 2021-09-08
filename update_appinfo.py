#!/usr/bin/env python3
from os import makedirs, listdir, path
from steam.client import SteamClient
from steam.core.msg import MsgProto
from steam.enums.emsg import EMsg
from steam.webapi import WebAPI
from sys import argv

if __name__ == "__main__":
    # Create directories
    makedirs("./appinfo", exist_ok=True)
    makedirs("./depots", exist_ok=True)

    steam_client = SteamClient()
    print("Connecting to the Steam network...")
    steam_client.connect()
    print("Logging in...")
    steam_client.anonymous_login()

    highest_changenumber = 0
    if path.exists("./last_change.txt"):
        with open("./last_change.txt", "r") as f:
            highest_changenumber = int(f.read())
    else:
        # if we haven't run get_appinfo yet, just find the last changenumber we downloaded
        for file in listdir("./appinfo"):
            if not file.endswith(".vdf"): continue
            changenumber = int(file.split("_")[1].replace(".vdf", ""))
            if changenumber > highest_changenumber:
                highest_changenumber = changenumber
    msg = MsgProto(EMsg.ClientPICSChangesSinceRequest)
    msg.body.since_change_number = highest_changenumber
    msg.body.send_app_info_changes = True
    print("Asking Steam PICS for changes since %s..." % (highest_changenumber))
    response = steam_client.wait_event(steam_client.send_job(msg))[0].body
    if response.force_full_app_update:
        print("Your appinfo is too old to get changes. Please redownload by "
            "running get_appinfo.py.")
        exit(1)
    msg = MsgProto(EMsg.ClientPICSProductInfoRequest)
    print("Latest change:", response.current_change_number)
    with open("./last_change.txt", "w") as f:
        f.write(str(response.current_change_number))
    for change in response.app_changes:
        if not change.needs_token:
            msg.body.apps.add().appid = change.appid
    for appinfo_response in steam_client.wait_event(steam_client.send_job(msg),
            15)[0].body.apps:
        # Write vdf appinfo to disk
        appinfo_path = "./appinfo/%s_%s.vdf" % (appinfo_response.appid,
                appinfo_response.change_number)
        if not path.exists(appinfo_path):
            with open(appinfo_path, "wb") as f:
                f.write(appinfo_response.buffer[:-1])
                print("Saved appinfo for app", appinfo_response.appid,
                        "changenumber", appinfo_response.change_number)
