#!/usr/bin/env python3
from argparse import ArgumentParser
from binascii import hexlify
from datetime import datetime
from hashlib import sha1
from io import BytesIO
from os import makedirs, remove
from os.path import dirname
from pathlib import Path
from struct import unpack
from sys import argv
from zipfile import ZipFile
import lzma

if __name__ == "__main__": # exit before we import our shit if the args are wrong
    parser = ArgumentParser(description='Extract downloaded depots.')
    parser.add_argument('depotid', type=int)
    parser.add_argument('manifestid', type=int)
    parser.add_argument('depotkey', type=str)
    parser.add_argument('-d', dest="dry_run", help="dry run: verify chunks without extracting", action="store_true")
    args = parser.parse_args()

from steam.client import SteamClient
from steam.client.cdn import CDNClient
from steam.core.manifest import DepotManifest
from steam.core.crypto import symmetric_decrypt

if __name__ == "__main__":
    args.depotkey = bytes.fromhex(args.depotkey)
    steam_client = SteamClient()
    c = CDNClient(steam_client)
    path = "./depots/%s/" % args.depotid
    manifest = None
    with open(path + "%s.zip" % args.manifestid, "rb") as f:
        manifest = DepotManifest(f.read())
    manifest.decrypt_filenames(args.depotkey)

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
            for chunk in file.chunks:
                chunkhex = hexlify(chunk.sha).decode()
                with open(path + chunkhex, "rb") as chunkfile:
                    decrypted = symmetric_decrypt(chunkfile.read(), args.depotkey)
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
