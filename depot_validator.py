#!/usr/bin/env python3
from argparse import ArgumentParser
from binascii import hexlify, unhexlify
from datetime import datetime
from fnmatch import fnmatch
from glob import glob
from hashlib import sha1
from io import BytesIO
from os import scandir, makedirs, remove
from os.path import dirname, exists
from pathlib import Path
from struct import unpack
from sys import argv
from zipfile import ZipFile
import lzma

if __name__ == "__main__": # exit before we import our shit if the args are wrong
    parser = ArgumentParser(description='Extract downloaded depots.')
    parser.add_argument('depotid', type=int)
    parser.add_argument('depotkey', type=str, nargs='?')
    parser.add_argument('-b', dest="backup", help="Path to a .csd backup file to extract (the manifest must also be present in the depots folder)", nargs='?')
    args = parser.parse_args()

from steam.core.manifest import DepotManifest
from steam.core.crypto import symmetric_decrypt
from chunkstore import Chunkstore

if __name__ == "__main__":
    path = "./depots/%s/" % args.depotid
    keyfile = "./keys/%s.depotkey" % args.depotid
    if args.depotkey:
        args.depotkey = bytes.fromhex(args.depotkey)
    elif exists(keyfile):
        with open(keyfile, "rb") as f:
            args.depotkey = f.read()
    elif exists("./depot_keys.txt"):
        with open("./depot_keys.txt", "r", encoding="utf-8") as f:
            for line in f.read().split("\n"):
                line = line.split("\t")
                try:
                    if int(line[0]) == args.depotid:
                        args.depotkey = bytes.fromhex(line[2])
                        break
                except ValueError:
                    pass
            if not args.depotkey:
                print("\033[31mERROR: files are encrypted, but no depot key was specified and no key for this depot exists in depot_keys.txt\033[0m")
                exit(1)
    else:
        print("\033[31mERROR: files are encrypted, but no depot key was specified and no depot_keys.txt or depotkey file exists\033[0m")
        exit(1)

    chunks = {}
    if args.backup:
        chunkstores = {}
        chunks_by_store = {}
        for csm in glob(args.backup.replace("_1.csm","").replace("_1.csd","") + "_*.csm"):
            chunkstore = Chunkstore(csm)
            chunkstore.unpack()
            for chunk, _ in chunkstore.chunks.items():
                chunks[chunk] = _
                chunks_by_store[chunk] = csm
            chunkstores[csm] = chunkstore
    else:
        chunkFiles = [data.name for data in scandir(path) if data.is_file()
        and not data.name.endswith(".zip")]
        for name in chunkFiles: chunks[name] = 0

    # print(f"{len(chunks)}")

    def is_hex(s):
        try:
            unhexlify(s)
            return True
        except:
            return False

    badfiles = []
 
    for file, value in chunks.items():
        try:
                if args.backup:
                    chunkhex = hexlify(file).decode()
                    chunk_data = None
                    is_encrypted = False
                    try:
                        chunkstore = chunkstores[chunks_by_store[file]]
                        chunk_data = chunkstore.get_chunk(file)
                        is_encrypted = chunkstore.is_encrypted
                    except Exception as e:
                        print(f"\033[31mError retrieving chunk\033[0m {chunkhex}: {e}")
                        ##breakpoint()
                        continue
                    if is_encrypted:
                        if args.depotkey:
                            decrypted = symmetric_decrypt(chunk_data, args.depotkey)
                        else:
                            print("\033[31mERROR: chunk %s is encrypted, but no depot key was specified\033[0m" % chunkhex)
                            exit(1)
                    else:
                        decrypted = chunk_data
                        chunk_data = None

                else:
                    chunkhex = hexlify(unhexlify(file.replace("_decrypted", ""))).decode()
                    if exists(path + chunkhex):
                        with open(path + chunkhex, "rb") as chunkfile:
                            if args.depotkey:
                                try:
                                    decrypted = symmetric_decrypt(chunkfile.read(), args.depotkey)
                                except ValueError as e:
                                    print(f"{e}")
                                    print(f"\033[31mError, unable to decrypt file:\033[0m {chunkhex}")
                                    badfiles.append(chunkhex)
                                    continue
                            else:
                                print("\033[31mERROR: chunk %s is encrypted, but no depot key was specified\033[0m" % chunkhex)
                                exit(1)
                    elif exists(path + chunkhex + "_decrypted"):
                        with open(path + chunkhex + "_decrypted", "rb") as chunkfile:
                            decrypted = chunkfile.read()
                    else:
                        print("missing chunk " + chunkhex)
                        continue
                decompressed = None
                if decrypted[:2] == b'VZ': # LZMA
                    decompressedSize = unpack('<i', decrypted[-6:-2])[0]
                    print("Testing (LZMA) from chunk", chunkhex, "Size:", decompressedSize)
                    try:
                        decompressed = lzma.LZMADecompressor(lzma.FORMAT_RAW, filters=[lzma._decode_filter_properties(lzma.FILTER_LZMA1, decrypted[7:12])]).decompress(decrypted[12:-10])[:decompressedSize]
                    except lzma.LZMAError as e:
                        print(f"\033[31mFailed to decompress:\033[0m {chunkhex}")
                        print(f"\033[31mError:\033[0m {e}")
                        badfiles.append(chunkhex)
                        continue
                elif decrypted[:2] == b'PK': # Zip
                    print("Testing (Zip) from chunk", chunkhex)
                    zipfile = ZipFile(BytesIO(decrypted))
                    decompressed = zipfile.read(zipfile.filelist[0])
                else:
                    print("\033[31mERROR: unknown archive type\033[0m", decrypted[:2].decode())
                    badfiles.append(chunkhex)
                    continue
                    #exit(1)
                sha = sha1(decompressed)
                if sha.digest() != unhexlify(chunkhex):
                    print("\033[31mERROR: sha1 checksum mismatch\033[0m (expected %s, got %s)" % (chunkhex, sha.hexdigest()))
                    badfiles.append(chunkhex)
        except IsADirectoryError:
            pass
    for bad in badfiles:
        print(f"{bad}")