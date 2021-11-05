#!/usr/bin/env python3
import requests as r
from argparse import ArgumentParser
from vdf import loads
from sys import argv
from os import makedirs, listdir
from os.path import exists, basename
from hashlib import sha256
from re import compile

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
    print("Downloading packages for client version %s" % client_manifest[platform]['version'])
    del client_manifest[platform]['version']
    for package_name, package in client_manifest[platform].items():
        needs_download = True
        if exists("./clientpackages/" + package['file']):
            with open("./clientpackages/" + package['file'], "rb") as f:
                if (sha256(f.read()).hexdigest()) == package['sha2']:
                    print("Package", package_name, "already up-to-date")
                    needs_download = False
        if needs_download:
                response = r.get(CDN_ROOT + package['file'])
                if response.ok:
                    with open("./clientpackages/" + package['file'], "wb") as f:
                        f.write(response.content)
                    print("Saved package", package_name)
                else:
                    print(f"Unable to download package {package_name}: {response.status_code}")
                    return False
    return True

if __name__ == "__main__":
    parser = ArgumentParser(description="Downloads a version of the Steam client from CDN")
    parser.add_argument("clientname", nargs="?", help="name of the client to download (e.g. \"steam_client_win32\")", default="steam_client_win32")
    parser.add_argument("-d", dest="dry_run", help="dry run: download client manifest but don't download packages", action="store_true")
    parser.add_argument("-l", dest="local", help="don't download a new manifest, just try to download packages for manifests that have already been downloaded", action="store_true")
    args = parser.parse_args()
    if args.dry_run and args.local:
        print("invalid combination of arguments")
        parser.print_help()
        exit(1)
    elif args.local:
        pattern = compile("_\d+$")
        if exists(args.clientname):
            platform = pattern.sub("", basename(args.clientname)).split("_")
            platform = platform[len(platform) - 1]
            with open(args.clientname, "r") as f:
                exit(0 if download_packages(loads(f.read()), platform) else 1)
        elif exists("./clientmanifests/" + args.clientname):
            platform = pattern.sub("", basename("./clientmanifests/" + args.clientname)).split("_")
            platform = platform[len(platform) - 1]
            with open("./clientmanifests/" + args.clientname, "r") as f:
                exit(0 if download_packages(loads(f.read()), platform) else 1)
        else:
            # try to find the newest manifest we downloaded
            highest = 0
            for file in listdir("./clientmanifests/"):
                if pattern.sub("", file) == args.clientname:
                    match = pattern.search(file)
                    version = int(file[match.start() + 1:match.end()])
                    if version > highest:
                        highest = version
            if highest == 0:
                print("can't find manifest " + args.clientname)
                exit(1)
            platform = basename("./clientmanifests/" + args.clientname).split("_")
            platform = platform[len(platform) - 1]
            with open("./clientmanifests/%s_%s" % (args.clientname, highest), "r") as f:
                exit(0 if download_packages(loads(f.read()), platform) else 1)
    elif args.dry_run:
        save_client_manifest(args.clientname)
    else:
        exit(0 if download_packages(*save_client_manifest(args.clientname)) else 1)
