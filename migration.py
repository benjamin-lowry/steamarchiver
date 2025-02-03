# temporary (rough) script to migrate from old storage format to new
from binascii import unhexlify
from os import makedirs, rename
from os.path import exists, basename, dirname, join
from glob import glob

migration_needed = lambda: exists("./depots")

def migrate():
    rename("./depots/", "./depot/")
    num_manifests = 0
    num_chunks = 0
    num_keys = 0
    # Move manifests and chunks
    for depot_dir in glob("./depot/*/"):
        depot_id = int(basename(dirname(depot_dir)))
        # Move manifests
        makedirs(join(depot_dir, "manifest"), exist_ok=True)
        for manifest_file in glob(join(depot_dir, "*.zip")):
            rename(manifest_file, join(depot_dir, "manifest", basename(manifest_file).replace(".zip", ".manif5")))
            num_manifests += 1
        # All files left should be chunks, move those
        makedirs(join(depot_dir, "chunk"), exist_ok=True)
        for file in glob(join(depot_dir, "*")):
            if basename(file) in ["manifest", "chunk"]: continue
            rename(file, join(depot_dir, "chunk", basename(file)))
            num_chunks += 1
    # Move depot keys
    if exists("./depot_keys.txt"):
        with open("./depot_keys.txt", "r") as f:
            for line in f:
                split = line.split("\t")
                depot_id = split[0]
                key = unhexlify(split[2].strip())
                makedirs(join("./depot/", depot_id), exist_ok=True)
                target = join("./depot/", depot_id, depot_id + ".depotkey")
                if not exists(target):
                    with open(target, "wb") as keyfile:
                        keyfile.write(key)
                        num_keys += 1
    print("migrated", num_manifests, "manifests,", num_chunks, "chunks,", num_keys, "keys")

if __name__ == "__main__":
    if migration_needed(): migrate()
    else: print("no migration needed")
