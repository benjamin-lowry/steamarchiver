#!/usr/bin/env python3
from binascii import hexlify
from steam.client import SteamClient
from steam.core.msg import MsgProto
from steam.enums.emsg import EMsg
from os.path import exists
from sys import argv
from vdf import loads

if __name__ == "__main__":
    steam_client = SteamClient()
    print("Connecting to the Steam network...")
    steam_client.connect()
    print("Logging in...")
    if len(argv) == 1:
        steam_client.cli_login()
    elif len(argv) == 2:
        if argv[1] == "anonymous":
            steam_client.anonymous_login()
            print("Logged in anonymously")
        else:
            steam_client.cli_login(username=argv[1])
    elif len(argv) == 3:
        steam_client.cli_login(username=argv[1], password=argv[2])
        print("Logged in as", argv[1])
    elif len(argv) == 4:
        steam_client.login(username=argv[1], password=argv[2], two_factor_code=argv[3], auth_code=argv[3])
    else:
        print("usage:", argv[0], "[username password steam_guard_code]")
        exit(1)
    licensed_packages = []
    licensed_apps = []
    licensed_depots = []
    if not steam_client.licenses:
        licensed_packages = [17906] # if we don't have a license list, we're an anonymous account
    else:
        for license in steam_client.licenses.values():
            print("Found license for package %s" % license.package_id)
            licensed_packages.append(license.package_id)
    product_info = steam_client.get_product_info(packages=licensed_packages)
    for package in product_info['packages'].values():
        for depot in package['depotids'].values():
            print("Found license for depot %s" % depot)
            licensed_depots.append(depot)
        for app in package['appids'].values():
            print("Found license for app %s" % app)
            licensed_apps.append(app)

    msg = MsgProto(EMsg.ClientPICSProductInfoRequest)
    for app in licensed_apps:
        msg.body.apps.add().appid = app
    job = steam_client.send_job(msg)
    appinfo_response = []
    response = steam_client.wait_event(job)[0].body
    for app in response.apps:
        appinfo_response.append(app)
    while response.response_pending:
        response = steam_client.wait_event(job)[0].body
        for app in response.apps:
            appinfo_response.append(app)
    app_dict = {}
    for app in appinfo_response:
        appinfo_path = "./appinfo/%s_%s.vdf" % (app.appid, app.change_number)
        app_dict[app.appid] = loads(app.buffer[:-1].decode('utf-8', 'replace'))['appinfo']
        if not exists(appinfo_path):
            with open(appinfo_path, "wb") as f:
                f.write(app.buffer[:-1])
            try:
                print("Saved appinfo for app", app.appid, "changenumber", app.change_number, app_dict[app.appid]['common']['name'])
            except KeyError:
                print("Saved appinfo for app", app.appid, "changenumber", app.change_number)

    keys_saved = []
    if exists("./depot_keys.txt"):
        with open("./depot_keys.txt", "r", encoding="utf-8") as f:
            for line in f.read().split("\n"):
                try:
                    keys_saved.append(int((line.split("\t")[0])))
                except ValueError:
                    continue
        print("%s keys already saved in depot_keys.txt" % len(keys_saved))
    with open("./depot_keys.txt", "a", encoding="utf-8", newline="\n") as f:
        for app, app_info in app_dict.items():
            if not app in licensed_apps:
                continue
            if not 'depots' in app_info:
                continue
            if not app in app_info['depots']:
                app_info['depots'][app] = {'name': app_info['common']['name']}
            for depot, info in app_info['depots'].items():
                try:
                    depot = int(depot)
                except ValueError:
                    continue
                if depot in keys_saved:
                    print("skipping previously saved key for depot", depot)
                    continue
                if (depot in licensed_depots) or (depot in licensed_apps):
                    try:
                        key = steam_client.get_depot_key(app, depot).depot_encryption_key
                    except AttributeError:
                        print("error getting key for depot", depot)
                        continue
                    else:
                        keys_saved.append(depot)
                        if key != b'':
                            key_hex = hexlify(key).decode()
                            if 'name' in info.keys():
                                f.write("%s\t\t%s\t%s" % (depot, key_hex, info['name']) + "\n")
                                print("%s\t\t%s\t%s" % (depot, key_hex, info['name']))
                            else:
                                f.write("%s\t\t%s" % (depot, key_hex) + "\n")
                                print("%s\t\t%s" % (depot, key_hex))
