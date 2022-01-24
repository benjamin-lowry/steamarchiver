#!/usr/bin/env python3
from argparse import ArgumentParser
from binascii import hexlify
from datetime import datetime
from hashlib import sha1
from io import BytesIO
from os import makedirs, remove
from os.path import dirname, exists
from pathlib import Path
from struct import unpack
from sys import argv
from zipfile import ZipFile
import lzma

if __name__ == "__main__": # exit before we import our shit if the args are wrong
    parser = ArgumentParser(description='Extract downloaded depots.')
    parser.add_argument('depotid', type=int)
    parser.add_argument('manifestid', type=int)
    parser.add_argument('depotkey', type=str, nargs='?')
    parser.add_argument('-d', dest="dry_run", help="dry run: verify chunks without extracting", action="store_true")
    args = parser.parse_args()

from steam.core.manifest import DepotManifest
from steam.core.crypto import symmetric_decrypt

if __name__ == "__main__":
    path = "./depots/%s/" % args.depotid
    manifest = None
    with open(path + "%s.zip" % args.manifestid, "rb") as f:
        manifest = DepotManifest(f.read())
    if args.depotkey:
        args.depotkey = bytes.fromhex(args.depotkey)
        if manifest.filenames_encrypted:
            manifest.decrypt_filenames(args.depotkey)
    elif manifest.filenames_encrypted:
            if exists("./depot_keys.txt"):
                with open("./depot_keys.txt", "r", encoding="utf-8") as f:
                    for line in f.read().split("\n"):
                        line = line.split("\t")
                        if int(line[0]) == args.depotid:
                            args.depotkey = bytes.fromhex(line[2])
                            manifest.decrypt_filenames(args.depotkey)
                            break
                    if not args.depotkey:
                        print("ERROR: manifest has encrypted filenames, but no depot key was specified and no key for this depot exists in depot_keys.txt")
                        exit(1)
            else:
                print("ERROR: manifest has encrypted filenames, but no depot key was specified and no depot_keys.txt exists")
                exit(1)

    for file in manifest.iter_files():
        target = "./extract/" + dirname(file.filename)
        if not args.dry_run:
            try:
                makedirs(target, exist_ok=True)
            except FileExistsError:
                remove(target)
                makedirs(target, exist_ok=True)
            except NotADirectoryError:
                # oh my fucking god
                while True:
                    try:
                        remove(Path(target).parent)
                    except IsADirectoryError:
                        pass
                    try:
                        makedirs(target, exist_ok=True)
                    except NotADirectoryError or FileExistsError:
                        continue
                    break
        try:
            for chunk in sorted(file.chunks, key = lambda chunk: chunk.offset):
                chunkhex = hexlify(chunk.sha).decode()
                if exists(path + chunkhex):
                    with open(path + chunkhex, "rb") as chunkfile:
                        if args.depotkey:
                            decrypted = symmetric_decrypt(chunkfile.read(), args.depotkey)
                        else:
                            print("ERROR: chunk %s is encrypted, but no depot key was specified" % chunkhex)
                            exit(1)
                elif exists(path + chunkhex + "_decrypted"):
                    with open(path + chunkhex + "_decrypted", "rb") as chunkfile:
                        decrypted = chunkfile.read()
                else:
                    print("missing chunk " + chunkhex)
                    continue
                decompressed = None
                if decrypted[:2] == b'VZ': # LZMA
                    if args.dry_run:
                        print("Testing", file.filename, "(LZMA) from chunk", chunkhex)
                    else:
                        print("Extracting", file.filename, "(LZMA) from chunk", chunkhex)
                    decompressed = lzma.LZMADecompressor(lzma.FORMAT_RAW, filters=[lzma._decode_filter_properties(lzma.FILTER_LZMA1, decrypted[7:12])]).decompress(decrypted[12:-9])[:chunk.cb_original]
                elif decrypted[:2] == b'PK': # Zip
                    if args.dry_run:
                        print("Testing", file.filename, "(Zip) from chunk", chunkhex)
                    else:
                        print("Extracting", file.filename, "(Zip) from chunk", chunkhex)
                    zipfile = ZipFile(BytesIO(decrypted))
                    decompressed = zipfile.read(zipfile.filelist[0])
                else:
                    print("ERROR: unknown archive type", decrypted[:2].decode())
                    exit(1)
                sha = sha1(decompressed)
                if sha.digest() != chunk.sha:
                    print("ERROR: sha1 checksum mismatch (expected %s, got %s)" % (hexlify(chunk.sha).decode(), sha.hexdigest()))
                if not args.dry_run:
                    with open("./extract/" + file.filename, "ab") as f:
                        f.seek(chunk.offset)
                        f.write(decompressed)
        except IsADirectoryError:
            pass
