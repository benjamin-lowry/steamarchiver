#!/usr/bin/env python3
from argparse import ArgumentParser
from asyncio import run, gather, sleep
from binascii import hexlify
from datetime import datetime
from math import ceil
from os import makedirs, path, listdir
from sys import argv

if __name__ == "__main__": # exit before we import our shit if the args are wrong
    parser = ArgumentParser(description='Download Steam content depots for archival.\nDownloading apps: Specify an app to download all the depots for that app, or an app and depot ID to download the latest version of that depot (or a specific version if the manifest ID is specified.)\nDownloading workshop items: Use the -w flag to specify the ID of the workshop file to download.')
    parser.add_argument("appid", type=int, nargs='?', help="App ID to download depots for.")
    parser.add_argument("depotid", type=int, nargs='?', help="Depot ID to download.")
    manifest_group = parser.add_mutually_exclusive_group()
    manifest_group.add_argument("manifestid", type=int, nargs='?', help="Manifest ID to download.")
    manifest_group.add_argument("-w", type=int, nargs='?', help="Workshop file ID to download.", dest="workshop_id")
    parser.add_argument("-d", help="Dry run: download manifest (file metadata) without actually downloading files", dest="dry_run", action="store_true")
    parser.add_argument("-l", help="Use latest local appinfo instead of trying to download", dest="local_appinfo", action="store_true")
    parser.add_argument("-c", type=int, help="Number of concurrent downloads to perform at once, default 10", dest="connection_limit", default=10)
    parser.add_argument("-s", type=str, help="Specify a specific server URL instead of automatically selecting one, e.g. https://steampipe.akamaized.net", nargs='?', dest="server")
    parser.add_argument("-i", help="Log into a Steam account interactively.", dest="interactive", action="store_true")
    parser.add_argument("-u", type=str, help="Username for non-interactive login", dest="username", nargs="?")
    parser.add_argument("-p", type=str, help="Password for non-interactive login", dest="password", nargs="?")
    args = parser.parse_args()
    if args.connection_limit < 1:
        print("connection limit must be at least 1")
        parser.print_help()
        exit(1)
    if not args.appid and not args.workshop_id:
        print("must specify at least one appid or workshop file id")
        parser.print_help()
        exit(1)
    if args.appid and args.workshop_id:
        print("must specify only app or workshop item, not both")
        parser.print_help()
        exit(1)

from steam.client import SteamClient
from steam.client.cdn import CDNClient, CDNDepotManifest
from steam.core.msg import MsgProto
from steam.enums import EResult
from steam.enums.emsg import EMsg
from steam.exceptions import SteamError
from steam.protobufs.content_manifest_pb2 import ContentManifestPayload
from vdf import loads
from aiohttp import ClientSession
from login import auto_login

def archive_manifest(manifest, c, name="unknown", dry_run=False, server_override=None):
    if not manifest:
        return False
    print("Archiving", manifest.depot_id, "(%s)" % (name), "gid", manifest.gid, "from", datetime.fromtimestamp(manifest.creation_time))
    dest = "./depots/" + str(manifest.depot_id) + "/"
    makedirs(dest, exist_ok=True)
    if dry_run:
        print("Not downloading chunks (dry run)")
        return True
    known_chunks = []
    for file in manifest.payload.mappings:
        for chunk in file.chunks:
            known_chunks.append(chunk.sha)
    print("Beginning to download", len(known_chunks), "encrypted", "chunk" if len(known_chunks) == 1 else "chunks")
    class download_state():
        def __init__(self):
            self.chunks_dled = 0
            self.chunks_skipped = 0
            self.bytes = 0
    download_state = download_state()
    async def dl_worker(chunks, download_state, servers):
        server = servers[0]
        async with ClientSession() as session:
            for index, chunk in enumerate(chunks):
                if path.exists(dest + hexlify(chunk).decode()):
                    download_state.chunks_skipped += 1
                    del chunks[index]
            for chunk in chunks:
                chunk_str = hexlify(chunk).decode()
                if path.exists(dest + chunk_str):
                    download_state.chunks_skipped += 1
                    continue
                with open(dest + chunk_str, "wb") as f:
                    while True:
                        try:
                            if server_override:
                                request_url = "%s/depot/%s/chunk/%s" % (server_override, manifest.depot_id, chunk_str)
                                host = server_override
                            else:
                                request_url = "%s://%s:%s/depot/%s/chunk/%s" % ("https" if server.https else "http",
                                    server.host,
                                    server.port,
                                    manifest.depot_id,
                                    chunk_str)
                                host = ("https" if server.https else "http") + "://" + server.host
                            async with session.get(request_url) as response:
                                if response.ok:
                                    download_state.bytes += response.content_length
                                    f.write(await response.content.read())
                                    break
                                elif 400 <= response.status < 500:
                                    print(f"error: received status code {response.status} (on chunk {chunk_str}, server {host})")
                                    exit(1)
                        except Exception as e:
                            print("rotating to next server:", e)
                        servers.rotate(-1)
                        server = servers[0]
                        await sleep(0.5)
                download_state.chunks_dled += 1
    async def summary_printer(download_state):
        averages = []
        last_msg_length = 0
        while download_state.chunks_dled + download_state.chunks_skipped != len(known_chunks):
            averages.append(download_state.bytes)
            download_state.bytes = 0
            if len(averages) == 6:
                del averages[0]
            speed = 0
            for average in averages:
                speed += average
            speed = round(speed / len(averages) / 1000000, 2)
            msg = f"\rDownloading at {speed}MB/s ({download_state.chunks_dled + download_state.chunks_skipped}/{len(known_chunks)})"
            if last_msg_length > len(msg):
                whitespace = " " * (last_msg_length - len(msg))
            else:
                whitespace = ""
            print(msg + whitespace,end="")
            last_msg_length = len(msg)
            await sleep(1)

    async def run_workers(download_state):
        workers = [summary_printer(download_state)]
        chunk_size = int(ceil(len(known_chunks)/args.connection_limit))
        for i in range(args.connection_limit):
            workers.append(dl_worker(known_chunks[i * chunk_size:i * chunk_size + chunk_size], download_state, c.servers.copy()))
        await gather(*workers)

    run(run_workers(download_state))
    print("\nFinished downloading", manifest.depot_id, "(%s)" % (name), "gid", manifest.gid, "from", datetime.fromtimestamp(manifest.creation_time))
    print("Downloaded %s %s and skipped %s" % (download_state.chunks_dled, "chunk" if download_state.chunks_dled == 1 else "chunks", download_state.chunks_skipped))
    return True

def try_load_manifest(appid, depotid, manifestid):
    print(f"Getting a manifest for app {appid} depot {depotid} gid {manifestid}")
    dest = "./depots/%s/%s.zip" % (depotid, manifestid)
    makedirs("./depots/%s" % depotid, exist_ok=True)
    if path.exists(dest):
        with open(dest, "rb") as f:
            manifest = CDNDepotManifest(c, appid, f.read())
            print("Loaded cached manifest %s from disk" % manifestid)
    else:
        while True:
            try:
                manifest = c.get_manifest(appid, depotid, manifestid, decrypt=False, manifest_request_code=c.get_manifest_request_code(appid, depotid, manifestid))
                break
            except SteamError as e:
                if e.eresult == EResult.AccessDenied:
                    print(e.message)
                    print(f"Use the -i flag to log into a Steam account with access to this depot, or place a downloaded copy of the manifest at depots/{depotid}/{manifestid}.zip")
                    return False
                else:
                    print(e.message + ": " + str(e.eresult))
                    return False
        print("Downloaded manifest %s" % manifestid)
        print("Saving manifest...") # write manifest to disk. this will be a standard Zip with protobuf data inside
        with open(dest, "wb") as f:
            f.write(manifest.serialize())
    return manifest

if __name__ == "__main__":
    # Create directories
    makedirs("./appinfo", exist_ok=True)
    makedirs("./depots", exist_ok=True)

    steam_client = SteamClient()
    print("Connecting to the Steam network...")
    steam_client.connect()
    print("Logging in...")
    if args.interactive:
        auto_login(steam_client, fallback_anonymous=False, relogin=False)
    elif args.username:
        auto_login(steam_client, args.username, args.password)
    else:
        auto_login(steam_client)
    c = CDNClient(steam_client)
    if args.workshop_id and not args.appid:
        response = steam_client.send_um_and_wait("PublishedFile.GetDetails#1", {'publishedfileids':[args.workshop_id]})
        if response.header.eresult != EResult.OK:
            print("error: couldn't get workshop item info:", response.header.error_message)
            exit(1)
        file = response.body.publishedfiledetails[0]
        if file.result != EResult.OK:
            print("error: steam returned error", EResult(file.result))
            exit(1)
        print("Retrieved data for workshop item", file.title, "for app", file.consumer_appid, "(%s)" % file.app_name)
        if not file.hcontent_file:
            print("error: workshop item is not on SteamPipe")
            exit(1)
        if file.file_url:
            print("error: workshop item is not on SteamPipe: its download URL is", file.file_url)
            exit(1)
        archive_manifest(try_load_manifest(file.consumer_appid, file.consumer_appid, file.hcontent_file), c, file.title, args.dry_run, args.server)
        exit(0)

    # Fetch appinfo
    if args.local_appinfo:
        highest_changenumber = 0
        for file in listdir("./appinfo/"):
            if not file.endswith(".vdf"): continue
            if not file.startswith(str(args.appid) + "_"): continue
            changenumber = int(file.split("_")[1].replace(".vdf", ""))
            if changenumber > highest_changenumber:
                highest_changenumber = changenumber
        if highest_changenumber == 0:
            print("error: -l flag specified, but no local appinfo exists for app", args.appid)
            exit(1)
        appinfo_path = "./appinfo/%s_%s.vdf" % (args.appid, highest_changenumber)
    else:
        print("Fetching appinfo for", args.appid)
        msg = MsgProto(EMsg.ClientPICSProductInfoRequest)
        msg.body.apps.add().appid = args.appid
        appinfo_response = steam_client.wait_event(steam_client.send_job(msg))[0].body.apps[0]
        changenumber = appinfo_response.change_number
        # Write vdf appinfo to disk
        appinfo_path = "./appinfo/%s_%s.vdf" % (args.appid, changenumber)
    if path.exists(appinfo_path):
        with open(appinfo_path, "r", encoding="utf-8") as f:
            appinfo = loads(f.read())['appinfo']
        print("Loaded appinfo from", appinfo_path)
    else:
        with open(appinfo_path, "wb") as f:
            f.write(appinfo_response.buffer[:-1])
        print("Saved appinfo for app", args.appid, "changenumber", changenumber)
        # decode appinfo
        appinfo = loads(appinfo_response.buffer[:-1].decode('utf-8', 'replace'))['appinfo']
    if "public_only" in appinfo.keys():
        print("WARNING: this app has additional (private) info. The archive "
                "may not work due to this info being missing. To get this "
                "info, run get_appinfo.py on this app using an account "
                "authorized to access it.")

    if args.depotid:
        name = appinfo['depots'][str(args.depotid)]['name'] if 'name' in appinfo['depots'][str(args.depotid)] else 'unknown'
        if args.manifestid:
            print("Archiving", appinfo['common']['name'], "depot", args.depotid, "manifest", args.manifestid)
            exit(0 if archive_manifest(try_load_manifest(args.appid, args.depotid, args.manifestid), c, name, args.dry_run, args.server) else 1)
        else:
            print("Archiving", appinfo['common']['name'], "depot", args.depotid, "manifest", appinfo['depots'][str(args.depotid)]['manifests']['public'])
            manifest = int(appinfo['depots'][str(args.depotid)]['manifests']['public'])
            exit(0 if archive_manifest(try_load_manifest(args.appid, args.depotid, manifest), c, name, args.dry_run, args.server) else 1)
    else:
        print("Archiving all latest depots for", appinfo['common']['name'], "build", appinfo['depots']['branches']['public']['buildid'])
        exitcode = 0
        for depot in appinfo["depots"]:
            depotinfo = appinfo["depots"][depot]
            if not "manifests" in depotinfo or not "public" in depotinfo["manifests"]:
                continue
            success = archive_manifest(try_load_manifest(args.appid, depot, depotinfo["manifests"]["public"]), c, depotinfo["name"] if "name" in depotinfo else "unknown", args.dry_run, args.server)
            if not success and exitcode == 0:
                exitcode = 1
        exit(exitcode)
