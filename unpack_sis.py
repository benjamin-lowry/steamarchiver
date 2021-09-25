#!/usr/bin/env python3
from binascii import hexlify, unhexlify
from os import path, makedirs
from sys import argv
from struct import iter_unpack
from vdf import loads
from re import sub
from io import BytesIO

def unpack_sis(sku, chunkstore_path):
    need_manifests = {}
    chunkstore_path = sub(r'Disk_\d+', '', chunkstore_path)
    if "sku" in sku.keys():
        sku = sku["sku"]

    # unpack each depot
    highest_disk = 1
    for depot in sku["manifests"]:
        need_manifests[depot] = sku["manifests"][depot]
        makedirs("./depots/%s" % depot, exist_ok=True)
        for chunkstore in sku["chunkstores"][depot]:
            print("unpacking chunkstore %s" % chunkstore)
            target = chunkstore_path + "/%s_depotcache_%s" % (depot, chunkstore)
            if not path.exists(target + ".csm"):
                # maybe it's in a disk folder?
                target = chunkstore_path + "/Disk_%s/%s_depotcache_%s" % (chunkstore, depot, chunkstore)
                if not path.exists(target + ".csm"):
                    # try again with other disk folders?
                    disk = 1
                    while disk <= highest_disk:
                        target = chunkstore_path + "/Disk_%s/%s_depotcache_%s" % (disk, depot, chunkstore)
                        print("searching for depot %s in disk %s" % (depot, disk))
                        if path.exists(target + ".csm"):
                            break
                        disk += 1
                    if not path.exists(target + ".csm"):
                        # welp
                        print("couldn't find depot %s chunkstore %s" % (depot, chunkstore))
                        return False
                if int(chunkstore) > highest_disk:
                    highest_disk = int(chunkstore)
            # unpack this chunkstore
            with open(target + ".csm", "rb") as csmfile, open(target + ".csd", "rb") as csdfile:
                csm = csmfile.read()
                if csm[:4] != b"SCFS":
                    print("not a CSM file: " + (target + ".csm"))
                    return False
                csm = csm[0x14:]
                for chunk in iter_unpack("<20s Q 8s", csm):
                    sha = chunk[0]
                    offset = chunk[1]
                    print("extracting chunk %s from offset %s in file %s" % (hexlify(sha).decode(), offset, target + ".csd"))

                    # unfortunately valve don't save the length of each chunk,
                    # so instead we can just read bytes from the file til we
                    # find the zip eof magic.  we can assume the eof header
                    # will always be 0x16 (22) bytes because there will never
                    # be a zip comment.
                    csdfile.seek(offset)
                    while True:
                        byte = csdfile.read(1)
                        if byte == b"\x50":
                            potential_eof = csdfile.tell() - 1
                            if csdfile.read(3) == b"\x4b\x05\x06":
                                # found eof
                                length = potential_eof + 22 - offset
                                break
                    csdfile.seek(offset)
                    with open("./depots/%s/%s_decrypted" % (depot, hexlify(sha).decode()), "wb") as f:
                        print("writing %s bytes" % length)
                        f.write(csdfile.read(length))
    print("done unpacking, to extract with depot_extractor you will need these manifests:")
    for depot, manifest in need_manifests.items():
        print("depot %s manifest %s" % (depot, manifest))
    return True

if __name__ == "__main__":
    if len(argv) != 2:
        print("usage: " + argv[0] + " sku.sis")
        exit(1)
    if not path.exists(argv[1]):
        print("file not found: " + argv[1])
        exit(1)
    with open(argv[1], "r") as f:
        sku = loads(f.read())
    chunkstore_path = path.dirname(argv[1])
    if chunkstore_path == "":
        chunkstore_path = "."
    exit(0 if unpack_sis(sku, chunkstore_path) else 1)
