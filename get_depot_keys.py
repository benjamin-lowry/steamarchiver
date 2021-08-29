#!/usr/bin/env python3
from binascii import hexlify
from steam.client import SteamClient
from steam.core.msg import MsgProto
from steam.enums.emsg import EMsg
from vdf import loads

if __name__ == "__main__":
    steam_client = SteamClient()
    steam_client.connect()
    steam_client.cli_login()
    licensed_packages = []
    licensed_apps = []
    licensed_depots = []
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
        with open("./appinfo/" + str(app.appid) + "_" + str(app.change_number) + ".vdf", "wb") as f:
            f.write(app.buffer[:-1])
        app_dict[app.appid] = loads(app.buffer[:-1].decode('utf-8', 'replace'))['appinfo']
        try:
            print("Saved appinfo for app", app.appid, "changenumber", app.change_number, app_dict[app.appid]['common']['name'])
        except KeyError:
            print("Saved appinfo for app", app.appid, "changenumber", app.change_number)

    keys_saved = []
    with open("./depot_keys.txt", "w+") as f:
        for line in f.read().split("\n"):
            try:
                keys_saved.append(int((line.split("\t")[0])))
            except ValueError:
                pass
    with open("./depot_keys.txt", "a") as f:
        for app, app_info in app_dict.items():
            if not app in licensed_apps:
                continue
            if not 'depots' in app_info:
                continue
            for depot, info in app_info['depots'].items():
                try:
                    depot = int(depot)
                except ValueError:
                    continue
                if depot in keys_saved:
                    print("skipping previously saved key for depot", depot)
                    continue
                if depot in licensed_depots:
                    key = steam_client.get_depot_key(app, depot).depot_encryption_key
                    key_hex = hexlify(key).decode()
                    keys_saved.append(depot)
                    f.write("%s\t\t%s\t%s" % (depot, key_hex, info['name']) + "\n")
                    print("%s\t\t%s\t%s" % (depot, key_hex, info['name']))
