#!/usr/bin/env python3
from binascii import hexlify
from datetime import datetime
from os import makedirs, path
from sys import argv

if __name__ == "__main__": # exit before we import our shit if the args are wrong
    if len(argv) < 2 or len(argv) == 3:
        print("usage:", argv[0], "appid [depotid manifestid]")
        exit(1)

from steam.client import SteamClient
from steam.client.cdn import CDNClient, CDNDepotManifest
from steam.core.msg import MsgProto
from steam.enums.emsg import EMsg
from steam.protobufs.content_manifest_pb2 import ContentManifestPayload
from vdf import loads

def archive_manifest(manifest, c):
    name = manifest.name if manifest.name else "unknown"
    print("Archiving", manifest.depot_id, "(%s)" % (name), "gid", manifest.gid, "from", datetime.fromtimestamp(manifest.creation_time))
    dest = "./depots/" + str(manifest.depot_id) + "/"
    makedirs(dest, exist_ok=True)
    print("Saving manifest...") # write manifest to disk. this will be a standard Zip with protobuf data inside
    with open(dest + str(manifest.gid) + ".zip", "wb") as f:
        f.write(manifest.serialize())
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

if __name__ == "__main__":
    # Create directories
    makedirs("./appinfo", exist_ok=True)
    makedirs("./depots", exist_ok=True)

    appid = int(argv[1])
    if len(argv) == 4:
        depotid = int(argv[2])
        manifestid = int(argv[3])
    else:
        depotid = 0
        manifestid = 0

    steam_client = SteamClient()
    print("Connecting to the Steam network...")
    steam_client.connect()
    print("Logging in...")
    steam_client.anonymous_login()
    c = CDNClient(steam_client)

    # Fetch appinfo
    print("Fetching appinfo for", appid)
    msg = MsgProto(EMsg.ClientPICSProductInfoRequest)
    msg.body.apps.add().appid = appid
    appinfo_response = steam_client.wait_event(steam_client.send_job(msg))[0].body.apps[0]
    changenumber = appinfo_response.change_number
    # Write vdf appinfo to disk
    appinfo_path = "./appinfo/%s_%s.vdf" % (appid, changenumber)
    if not path.exists(appinfo_path):
        with open(appinfo_path, "wb") as f:
            f.write(appinfo_response.buffer[:-1])
            print("Saved appinfo for app", appid, "changenumber", changenumber)

    # decode appinfo
    appinfo = loads(appinfo_response.buffer[:-1].decode('utf-8', 'replace'))['appinfo']

    if depotid and manifestid:
        print("Archiving", appinfo['common']['name'], "depot", depotid, "manifest", manifestid)
        dest = "./depots/%s/%s.zip" % (depotid, manifestid)
        if path.exists(dest):
            with open(dest, "rb") as f:
                manifest = CDNDepotManifest(c, appid, f.read())
                print("Loaded cached manifest %s from disk" % manifestid)
        else:
            manifest = c.get_manifest(appid, depotid, manifestid, decrypt=False)
        archive_manifest(manifest, c)
    else:
        print("Archiving all latest depots for", appinfo['common']['name'], "build", appinfo['depots']['branches']['public']['buildid'])
        for manifest in c.get_manifests(appid, decrypt=False):
            breakpoint()
            archive_manifest(manifest, c)
