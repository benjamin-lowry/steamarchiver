#!/usr/bin/env python3
import requests as r
from vdf import loads
from sys import argv
from os import makedirs
from os.path import exists
from hashlib import sha256

# TODO: code to load cachedupdatehosts.vdf
CDN_ROOT = "https://steamcdn-a.akamaihd.net/client/"

def save_client_manifest(name):
    platform = name.split("_")
    platform = platform[len(platform) - 1]
    makedirs("./clientmanifests", exist_ok=True)
    response = r.get(CDN_ROOT + name)
    response.raise_for_status()
    keyvalues = loads(response.content.decode())
    manifest_name = name + "_" + keyvalues[platform]["version"]
    with open("./clientmanifests/" + manifest_name, "wb") as f:
        f.write(response.content)
        print("Saved client manifest", manifest_name)
    return keyvalues, platform

def download_packages(client_manifest, platform):
    makedirs("./clientpackages", exist_ok=True)
    del client_manifest[platform]['version']
    for package_name, package in client_manifest[platform].items():
        needs_download = True
        if exists("./clientpackages/" + package['file']):
            with open("./clientpackages/" + package['file'], "rb") as f:
                if (sha256(f.read()).hexdigest()) == package['sha2']:
                    print("Package", package_name, "already up-to-date")
                    needs_download = False
        if needs_download:
            with open("./clientpackages/" + package['file'], "wb") as f:
                f.write(r.get(CDN_ROOT + package['file']).content)
                print("Saved package", package_name)

if __name__ == "__main__":
    if len(argv) == 1:
        download_packages(*save_client_manifest("steam_client_win32"))
    elif len(argv) == 2:
        download_packages(*save_client_manifest(argv[1]))
    else:
        print("usage: %s [client type]" % argv[0])