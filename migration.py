# temporary (rough) script to migrate from old storage format to new
from binascii import unhexlify
from os import makedirs, rename
from os.path import exists, basename, dirname, join, isdir, relpath
from glob import glob

migration_needed = lambda: exists("./depots")

def move_files(source, target):
    num_manifests = 0
    skipped_manifests = 0
    
    num_chunks = 0
    skipped_chunks = 0
    
    # Move manifests and chunks
    for depot_dir in glob(join(source, "*/")):
        # Unused in this update nor the original script, but kept for reference
        # depot_id = int(basename(dirname(depot_dir)))
        
        # Calculate the relative path from the source directory
        relative_path = relpath(depot_dir, source)
        target_depot_dir = join(target, relative_path)
        # Move manifests
        makedirs(join(target_depot_dir, "manifest"), exist_ok=True)
        for manifest_file in glob(join(depot_dir, "*.zip")):
            target_manifest_file = join(target_depot_dir, "manifest", basename(manifest_file).replace(".zip", ".manif5"))
            if not exists(target_manifest_file):
                rename(manifest_file, target_manifest_file)
                num_manifests += 1
            else:
                skipped_manifests += 1
        # All files left should be chunks, move those
        makedirs(join(target_depot_dir, "chunk"), exist_ok=True)
        for file in glob(join(depot_dir, "*")):
            if basename(file) in ["manifest", "chunk"] or isdir(file): continue
            target_chunk_file = join(target_depot_dir, "chunk", basename(file))
            if not exists(target_chunk_file):
                rename(file, target_chunk_file)
                num_chunks += 1
            else:
                skipped_chunks += 1
    
    return num_manifests, num_chunks, skipped_chunks, skipped_manifests

def migrate():
    target_dir = "./depot/"
    source_dir = "./depots/"
    
    # If the target directory exists, we need to move the files instead of renaming the source directory,
    # as the target directory might contain files that need to be preserved, and attempting to rename the source
    # directory to the already existing target directory would result in an error.
    if exists(target_dir):
        num_manifests, num_chunks, skipped_chunks, skipped_manifests = move_files(source_dir, target_dir)
    else:
        rename(source_dir, target_dir)
        num_manifests, num_chunks, skipped_chunks, skipped_manifests = move_files(target_dir, target_dir)
    
    # Move depot keys
    num_keys = 0
    if exists("./depot_keys.txt"):
        with open("./depot_keys.txt", "r") as f:
            for line in f:
                split = line.split("\t")
                depot_id = split[0]
                key = unhexlify(split[2].strip())
                makedirs(join(target_dir, depot_id), exist_ok=True)
                target = join(target_dir, depot_id, depot_id + ".depotkey")
                if not exists(target):
                    with open(target, "wb") as keyfile:
                        keyfile.write(key)
                        num_keys += 1
    
    print(f"Migrated {num_manifests} manifests (Skipping {skipped_manifests}), {num_chunks} chunks (Skipping {skipped_chunks}), {num_keys} keys")
    
if __name__ == "__main__":
    if migration_needed(): migrate()
    else: print("no migration needed")
