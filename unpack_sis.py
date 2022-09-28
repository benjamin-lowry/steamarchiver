#!/usr/bin/env python3
from argparse import ArgumentParser
from binascii import hexlify, unhexlify
from io import BytesIO
from os import path, makedirs
from re import sub
from steam.core.crypto import symmetric_encrypt, symmetric_encrypt_with_iv
from struct import iter_unpack
from sys import argv
from vdf import loads

class Chunkstore():
    def __init__(self, filename):
        filename = filename.replace(".csd","").replace(".csm","")
        self.csmname = filename + ".csm"
        self.csdname = filename + ".csd"
        self.chunks = {}
        self.csdfile = None
        self.open()
        with open(self.csmname, "rb") as csmfile:
            self.csm = csmfile.read()
            if self.csm[:4] != b"SCFS":
                print("not a CSM file: " + (filename + ".csm"))
                return False
            self.depot = int.from_bytes(self.csm[0xc:0x10], byteorder='little', signed=False)
            self.is_encrypted = (self.csm[0x8:0xa] == b'\x03\x00')
    def __repr__(self):
        return f"Depot {self.depot} (encrypted: {self.is_encrypted}) from CSD file {self.csdname}"
    def unpack(self, unpacker=None):
        if unpacker: assert callable(unpacker)
        self.open()
        csm = self.csm[0x14:]
        for sha, offset, _, length in iter_unpack("<20s Q L L", csm):
            self.chunks[sha] = (offset, length)
            if unpacker: unpacker(self, sha, offset, length)
    def open(self):
        if not self.csdfile:
            self.csdfile = open(self.csdname, "rb")
    def close(self):
        if self.csdfile:
            self.csdfile.close()
        self.csdfile = None
    def get_chunk(self, sha):
        self.open()
        self.csdfile.seek(self.chunks[sha][0])
        return self.csdfile.read(self.chunks[sha][1])

def unpack_chunkstore(target, key=None, key_hex=None):
        if key == True:
            key, key_hex = find_key(depot)
        def unpacker(chunkstore, sha, offset, length):
            print("extracting chunk %s from offset %s in file %s" % (hexlify(sha).decode(), offset, target + ".csd"))
            chunkstore.csdfile.seek(offset)
            if key:
                with open("./depots/%s/%s" % (chunkstore.depot, hexlify(sha).decode()), "wb") as f:
                    print("writing %s bytes re-encrypted using key %s and random IV" % (length, key_hex))
                    f.write(symmetric_encrypt(chunkstore.csdfile.read(length), key))
            elif chunkstore.is_encrypted:
                with open("./depots/%s/%s" % (chunkstore.depot, hexlify(sha).decode()), "wb") as f:
                    print("writing %s bytes encrypted" % length)
                    f.write(chunkstore.csdfile.read(length))
            else:
                with open("./depots/%s/%s_decrypted" % (chunkstore.depot, hexlify(sha).decode()), "wb") as f:
                    print("writing %s bytes unencrypted" % length)
                    f.write(chunkstore.csdfile.read(length))
        chunkstore = Chunkstore(target)
        makedirs("./depots/%s" % chunkstore.depot, exist_ok=True)
        chunkstore.unpack(unpacker)

def find_key(depot):
    if path.exists("./depot_keys.txt"):
        with open("./depot_keys.txt", "r", encoding="utf-8") as f:
            for line in f.read().split("\n"):
                line = line.split("\t")
                if line[0] == depot:
                    key_hex = line[2]
                    return unhexlify(key_hex), key_hex
    if not key:
        print("couldn't find key for depot", depot)

def unpack_sis(sku, chunkstore_path, use_key = False):
    need_manifests = {}
    chunkstore_path = sub(r'Disk_\d+', '', chunkstore_path)
    if "sku" in sku.keys():
        sku = sku["sku"]

    # unpack each depot
    for depot in sku["manifests"]:
        key, key_hex = None, None
        if use_key and sku["backup"] == "1":
            key, key_hex = find_key(depot)
            breakpoint()
        need_manifests[depot] = sku["manifests"][depot]
        for chunkstore in sku["chunkstores"][depot]:
            print("unpacking chunkstore %s" % chunkstore)
            target = chunkstore_path + "/%s_depotcache_%s" % (depot, chunkstore)
            if not path.exists(target + ".csm"):
                # maybe it's in a disk folder?
                target = chunkstore_path + "/Disk_%s/%s_depotcache_%s" % (chunkstore, depot, chunkstore)
                if not path.exists(target + ".csm"):
                    # try again with other disk folders?
                    disk = 1
                    while disk <= int(sku["disks"]):
                        target = chunkstore_path + "/Disk_%s/%s_depotcache_%s" % (disk, depot, chunkstore)
                        print("searching for depot %s in disk %s" % (depot, disk))
                        if path.exists(target + ".csm"):
                            break
                        disk += 1
                    if not path.exists(target + ".csm"):
                        # welp
                        print("couldn't find depot %s chunkstore %s" % (depot, chunkstore))
                        return False
            # unpack this chunkstore
            unpack_chunkstore(target, key, key_hex)
    print("done unpacking, to extract with depot_extractor you will need these manifests:")
    for depot, manifest in need_manifests.items():
        print("depot %s manifest %s" % (depot, manifest))
    return True

if __name__ == "__main__":
    parser = ArgumentParser(description='Unpacks game data chunks from a SteamPipe retail master or game backup.')
    parser.add_argument("target", type=str, help="Path to the sku.sis file defining the master to unpack (or path to csd or csm file if only unpacking one chunkstore.)")
    parser.add_argument("-e", action='store_true', help="Re-encrypt the chunks with a key from depot_keys.txt (if one is available) after extracting. (The primary reason you would want to do this is to serve the chunks to a Steam client over a LAN cache.)", dest="key")
    args = parser.parse_args()
    if args.target.endswith(".sis"):
        with open(args.target, "r") as f:
            sku = loads(f.read())
        chunkstore_path = path.dirname(args.target)
        if chunkstore_path == "":
            chunkstore_path = "."
        exit(0 if unpack_sis(sku, chunkstore_path, args.key) else 1)
    else:
        unpack_chunkstore(args.target.replace(".csm","").replace(".csd",""), args.key)
