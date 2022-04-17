#!/usr/bin/env python3
from argparse import ArgumentParser
from binascii import hexlify, unhexlify
from os import scandir, makedirs
from struct import pack
from vdf import dumps
from sys import stderr

def pack_backup(depot, decrypted, destdir):
    csd_target = destdir + "/" + str(depot) + "_depotcache_1.csd"
    csm_target = destdir + "/" + str(depot) + "_depotcache_1.csm"
    depot_dir = "./depots/" + str(depot)

    if decrypted:
        chunk_match = lambda chunk: chunk.endswith("_decrypted")
    else:
        chunk_match = lambda chunk: not chunk.endswith("_decrypted")

    chunks = [chunk.name for chunk in scandir(depot_dir) if chunk.is_file()
            and not chunk.name.endswith(".zip")
            and chunk_match(chunk.name)]
    total_length = 0
    with open(csd_target, "wb") as csd, open(csm_target, "wb") as csm:
        # write CSM header
        csm.write(b"SCFS\x14\x00\x00\x00")
        if decrypted:
            csm.write(b"\x02\x00\x00\x00")
        else:
            csm.write(b"\x03\x00\x00\x00")
        csm.write(pack("<L L", depot, len(chunks)))
        # iterate over chunks
        chunks_added = 0
        for chunk in chunks:
            offset = csd.tell()

            with open("./depots/" + str(depot) + "/" + chunk, "rb") as chunkfile:
                # get length of chunk
                chunkfile.seek(0, 2)
                length = chunkfile.tell()
                total_length += length
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
    print("packed", len(chunks), "chunks")
    return total_length

if __name__ == "__main__":
    parser = ArgumentParser(description='Pack a SteamPipe backup (.csd/.csm files, and optionally an sku.sis file defining the backup) from individual chunks in the depots/ folder.')
    parser.add_argument("-a", dest="appid", type=int, help="App ID for sku file (if ommitted, no sku will be generated)", nargs="?")
    parser.add_argument("-d", dest="depots", metavar=('depot', 'manifest'), action="append", type=int, help="Depot ID to pack, can be used multiple times. Include a manifest ID too if generating an sku.sis", nargs='+')
    parser.add_argument("-n", dest="name", default="steamarchiver backup", type=str, help="Backup name")
    parser.add_argument("--decrypted", action='store_true', help="Use decrypted chunks to pack backup", dest="decrypted")
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
        size = pack_backup(depot, args.decrypted, args.destdir)
        if write_sku:
            sku["sku"]["chunkstores"][str(depot)] = {"1":str(size)}
    if write_sku:
        with open(args.destdir + "/sku.sis", "w") as skufile:
            skufile.write(dumps(sku))
            print("wrote sku.sis")
