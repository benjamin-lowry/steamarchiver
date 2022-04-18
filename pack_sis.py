#!/usr/bin/env python3
from argparse import ArgumentParser
from binascii import hexlify, unhexlify
from os import scandir, makedirs
from os.path import exists
from struct import pack, unpack, iter_unpack
from vdf import dumps
from sys import stderr

def pack_backup(depot, destdir, decrypted=False, no_update=False):
    csd_target = destdir + "/" + str(depot) + "_depotcache_1.csd"
    csm_target = destdir + "/" + str(depot) + "_depotcache_1.csm"
    depot_dir = "./depots/" + str(depot)
    previous_chunks = []
    existing_number_chunks = 0
    mode = "wb"

    if exists(csm_target) and exists(csd_target) and not no_update:
        with open(csd_target, "rb") as csd, open(csm_target, "rb") as csm:
            if csm.read(8) != b"SCFS\x14\x00\x00\x00":
                print("error: target", csm_target, "already exists and is not a CSM file", file=stderr)
                exit(1)
            if csm.read(1) == 0x03 and decrypted:
                print("error: target", csm_target, "already exists and contains encrypted chunks", file=stderr)
                exit(1)
            csm.seek(0xC)
            existing_depot, existing_number_chunks = unpack("<L L", csm.read(8))
            if existing_depot != depot:
                print("error: target", csm_target, "already exists and lists a different depot", file=stderr)
                exit(1)
            for sha, offset, _, length in iter_unpack("<20s Q L L", csm.read()):
                previous_chunks.append(hexlify(sha).decode())
        mode = "r+b"

    if decrypted:
        chunk_match = lambda chunk: chunk.endswith("_decrypted")
    else:
        chunk_match = lambda chunk: not chunk.endswith("_decrypted")

    def is_hex(s):
        try:
            unhexlify(s)
            return True
        except:
            return False

    chunks = [chunk.name for chunk in scandir(depot_dir) if chunk.is_file()
            and not chunk.name.endswith(".zip")
            and chunk_match(chunk.name)
            and is_hex(chunk.name)
            and not chunk.name in previous_chunks]
    with open(csd_target, mode) as csd, open(csm_target, mode) as csm:
        # write CSM header
        csm.write(b"SCFS\x14\x00\x00\x00")
        if decrypted:
            csm.write(b"\x02\x00\x00\x00")
        else:
            csm.write(b"\x03\x00\x00\x00")
        csm.write(pack("<L L", depot, len(chunks) + existing_number_chunks))
        csm.seek(0, 2) # make sure we're at the end of the csm file (in case we're writing to an existing csm)
        # iterate over chunks
        chunks_added = 0
        for chunk in chunks:
            csd.seek(0, 2)
            offset = csd.tell()

            with open("./depots/" + str(depot) + "/" + chunk, "rb") as chunkfile:
                # get length of chunk
                chunkfile.seek(0, 2)
                length = chunkfile.tell()
                chunkfile.seek(0)

                # write chunk content to csd
                csd.write(chunkfile.read())

            # write chunk location to csm
            if decrypted:
                csm.write(unhexlify(chunk.replace("_decrypted","")))
            else:
                csm.write(unhexlify(chunk))
            csm.write(pack("<Q L L", offset, 0, length))
            chunks_added += 1
            print(f"depot {depot}: added chunk {chunk} ({chunks_added}/{len(chunks)})")
        print("packed", len(chunks), "chunk" if len(chunks) == 1 else "chunks")
        csd.seek(0, 2)
        return csd.tell()

if __name__ == "__main__":
    parser = ArgumentParser(description='Pack a SteamPipe backup (.csd/.csm files, and optionally an sku.sis file defining the backup) from individual chunks in the depots/ folder.')
    parser.add_argument("-a", dest="appid", type=int, help="App ID for sku file (if ommitted, no sku will be generated)", nargs="?")
    parser.add_argument("-d", dest="depots", metavar=('depot', 'manifest'), action="append", type=int, help="Depot ID to pack, can be used multiple times. Include a manifest ID too if generating an sku.sis", nargs='+')
    parser.add_argument("-n", dest="name", default="steamarchiver backup", type=str, help="Backup name")
    parser.add_argument("--decrypted", action='store_true', help="Use decrypted chunks to pack backup", dest="decrypted")
    parser.add_argument("--no-update", action='store_true', help="If an existing backup is found, delete it instead of updating it", dest="no_update")
    parser.add_argument("--destdir", help="Directory to put sis/csm/csd files in", default=".")
    args = parser.parse_args()
    makedirs(args.destdir, exist_ok=True)
    if args.depots == None:
        print("must specify at least one depot", file=stderr)
        parser.print_usage()
        exit(1)
    sku = {}
    write_sku = False
    if args.appid != None:
        write_sku = True
        sku = {"sku":
                {"name":args.name,
                "disks":"1",
                "disk":"1",
                "backup":"1" if args.decrypted else "0",
                "contenttype":"3",
                "apps":{
                    "0":str(args.appid)
                    },
                "depots":{},
                "manifests":{},
                "chunkstores":{}
              }
        }
    for depot_tuple in args.depots:
        if len(depot_tuple) == 2:
            depot, manifest = depot_tuple
        else:
            depot = depot_tuple[0]
            manifest = False
        if write_sku:
            if not manifest:
                write_sku = False
                print("not generating sku.sis: no manifest specified for depot",depot)
            else:
                sku["sku"]["depots"][len(sku["sku"]["depots"])] = str(depot)
                sku["sku"]["manifests"][str(depot)] = str(manifest)
        size = pack_backup(depot, args.destdir, args.decrypted, args.no_update)
        if write_sku:
            sku["sku"]["chunkstores"][str(depot)] = {"1":str(size)}
    if write_sku:
        with open(args.destdir + "/sku.sis", "w") as skufile:
            skufile.write(dumps(sku))
            print("wrote sku.sis")
