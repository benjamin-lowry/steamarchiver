#!/usr/bin/env python3
from os import makedirs, path
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

    # Parse arguments
    appids = []
    if len(argv) > 1:
        del argv[0]
        for appid in argv:
            appids.append(int(appid))
    else:
        print("Fetching list of apps from WebAPI...")
        for app in WebAPI(None).ISteamApps.GetAppList_v2()['applist']['apps']:
            appids.append(app['appid'])

    # Write the current changenumber, for use later with update_appinfo
    with open("./last_change.txt", "w") as f:
        msg = MsgProto(EMsg.ClientPICSChangesSinceRequest)
        msg.body.since_change_number = 0
        response = steam_client.wait_event(steam_client.send_job(msg))[0].body
        print("Latest change:", response.current_change_number)
        f.write(str(response.current_change_number))

    # Fetch appinfo in groups of 30 (the maximum number of apps PICS will give
    # us in one message)
    for group in [appids[i:i + 30] for i in range(0, len(appids), 30)]:
        msg = MsgProto(EMsg.ClientPICSProductInfoRequest)
        for app in group:
            msg.body.apps.add().appid = app
        print("Asking Steam PICS for appinfo for %s %s..." % (len(msg.body.apps),
            "app" if len(msg.body.apps) == 1 else "apps"))
        while True:
            try:
                response = steam_client.wait_event(steam_client.send_job(msg), 15)[0].body
                break
            except TypeError:
                print("Timeout reached, retrying...")
        print("Received response from Steam PICS containing info for %s apps." %
                len(response.apps))
        for appinfo_response in response.apps:
            # Write vdf appinfo to disk
            appinfo_path = "./appinfo/%s_%s.vdf" % (appinfo_response.appid,
                    appinfo_response.change_number)
            if not path.exists(appinfo_path):
                with open(appinfo_path, "wb") as f:
                    f.write(appinfo_response.buffer[:-1])
                    print("Saved appinfo for app", appinfo_response.appid,
                            "changenumber", appinfo_response.change_number)
