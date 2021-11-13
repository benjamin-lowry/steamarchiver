#!/usr/bin/env python3
from argparse import ArgumentParser
from binascii import hexlify
from datetime import datetime
from os import makedirs, path
from sys import argv

if __name__ == "__main__": # exit before we import our shit if the args are wrong
    parser = ArgumentParser(description='Download Steam content depots for archival.\nSpecify an app to download all the depots for that app, or an app and depot ID to download the latest version of that depot (or a specific version if the manifest ID is specified.)')
    parser.add_argument("appid", type=int, help="App ID to download depots for.")
    parser.add_argument("depotid", type=int, nargs='?', help="Depot ID to download.")
    parser.add_argument("manifestid", type=int, nargs='?', help="Manifest ID to download.")
    parser.add_argument("-d", help="Dry run: download manifest (file metadata) without actually downloading files", dest="dry_run", action="store_true")
    args = parser.parse_args()

from steam.client import SteamClient
from steam.client.cdn import CDNClient, CDNDepotManifest
from steam.core.msg import MsgProto
from steam.enums.emsg import EMsg
from steam.protobufs.content_manifest_pb2 import ContentManifestPayload
from vdf import loads

def archive_manifest(manifest, c, dry_run=False):
    name = manifest.name if manifest.name else "unknown"
    print("Archiving", manifest.depot_id, "(%s)" % (name), "gid", manifest.gid, "from", datetime.fromtimestamp(manifest.creation_time))
    dest = "./depots/" + str(manifest.depot_id) + "/"
    makedirs(dest, exist_ok=True)
    print("Saving manifest...") # write manifest to disk. this will be a standard Zip with protobuf data inside
    with open(dest + str(manifest.gid) + ".zip", "wb") as f:
        f.write(manifest.serialize())
    if dry_run:
        print("Not downloading chunks (dry run)")
        return
    known_chunks = []
    for file in manifest.payload.mappings:
        for chunk in file.chunks:
            known_chunks.append(chunk.sha)
    print("Beginning to download", len(known_chunks), "encrypted chunks")
    chunks_dled, chunks_skipped = 0, 0
    for index, chunk in enumerate(known_chunks):
        chunk_str = hexlify(chunk).decode()
        if path.exists(dest + chunk_str):
            chunks_skipped += 1
            continue
        with open(dest + chunk_str, "wb") as f:
            f.write(c.cdn_cmd("depot", "%s/chunk/%s" % (manifest.depot_id, chunk_str)).content)
            chunks_dled += 1
        print("\rFinished download of chunk", chunk_str, "(%s/%s)" % (index + 1, len(known_chunks)),end="")
    print("\nFinished downloading", manifest.depot_id, "(%s)" % (manifest.name), "gid", manifest.gid, "from", datetime.fromtimestamp(manifest.creation_time))
    print("Downloaded %s chunks and skipped %s" % (chunks_dled, chunks_skipped))

def try_load_manifest(appid, depotid, manifestid):
    dest = "./depots/%s/%s.zip" % (depotid, manifestid)
    if path.exists(dest):
        with open(dest, "rb") as f:
            manifest = CDNDepotManifest(c, appid, f.read())
            print("Loaded cached manifest %s from disk" % manifestid)
    else:
        manifest = c.get_manifest(appid, depotid, manifestid, decrypt=False)
        print("Downloaded manifest %s" % manifestid)
    return manifest

if __name__ == "__main__":
    # Create directories
    makedirs("./appinfo", exist_ok=True)
    makedirs("./depots", exist_ok=True)

    steam_client = SteamClient()
    print("Connecting to the Steam network...")
    steam_client.connect()
    print("Logging in...")
    steam_client.anonymous_login()
    c = CDNClient(steam_client)

    # Fetch appinfo
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

    if args.depotid and args.manifestid:
        print("Archiving", appinfo['common']['name'], "depot", args.depotid, "manifest", args.manifestid)
        archive_manifest(try_load_manifest(args.appid, args.depotid, args.manifestid), c, args.dry_run)
    elif args.depotid:
        print("Archiving", appinfo['common']['name'], "depot", args.depotid, "manifest", appinfo['depots'][str(args.depotid)]['manifests']['public'])
        manifest = int(appinfo['depots'][str(args.depotid)]['manifests']['public'])
        archive_manifest(try_load_manifest(args.appid, args.depotid, manifest), c, args.dry_run)
    else:
        print("Archiving all latest depots for", appinfo['common']['name'], "build", appinfo['depots']['branches']['public']['buildid'])
        for manifest in c.get_manifests(args.appid, decrypt=False):
            archive_manifest(manifest, c, args.dry_run)
