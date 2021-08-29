#!/usr/bin/env python3
from binascii import hexlify
from datetime import datetime
from os import makedirs, remove
from os.path import dirname
from pathlib import Path
from struct import unpack
from sys import argv
from zipfile import ZipFile
from io import BytesIO
import lzma

if __name__ == "__main__": # exit before we import our shit if the args are wrong
    if len(argv) != 4:
        print("usage:", argv[0], "depotid manifestid depotkey")
        exit(1)

from steam.client import SteamClient
from steam.client.cdn import CDNClient
from steam.core.manifest import DepotManifest
from steam.core.crypto import symmetric_decrypt

if __name__ == "__main__":
    makedirs("./extract", exist_ok=True)
    depotid = int(argv[1])
    manifestid = int(argv[2])
    depotkey = bytes.fromhex(argv[3])
    steam_client = SteamClient()
    c = CDNClient(steam_client)
    path = "./depots/%s/" % depotid
    manifest = None
    with open(path + "%s.zip" % manifestid, "rb") as f:
        manifest = DepotManifest(f.read())
    manifest.decrypt_filenames(depotkey)

    for file in manifest.iter_files():
        target = "./extract/" + dirname(file.filename)
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
            with open("./extract/" + file.filename, "wb") as f:
                for chunk in file.chunks:
                    chunkhex = hexlify(chunk.sha).decode()
                    with open(path + chunkhex, "rb") as chunkfile:
                        decrypted = symmetric_decrypt(chunkfile.read(), depotkey)
                        decompressed = None
                        if decrypted[:2] == b'VZ': # LZMA
                            print("Extracting", file.filename, "(LZMA) from chunk", chunkhex)
                            decompressed = lzma.LZMADecompressor(lzma.FORMAT_RAW, filters=[lzma._decode_filter_properties(lzma.FILTER_LZMA1, decrypted[7:12])]).decompress(decrypted[12:-9])[:chunk.cb_original]
                        else:
                            print("Extracting", file.filename, "(Zip) from chunk", chunkhex)
                            zipfile = ZipFile(BytesIO(decrypted))
                            decompressed = zipfile.read(zipfile.filelist[0])
                    f.seek(chunk.offset)
                    f.write(decompressed)
        except IsADirectoryError:
            pass
