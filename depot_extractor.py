#!/usr/bin/env python3
"""
This script extracts downloaded depots from Steam, handling encrypted filenames and chunks, and supports multithreaded extraction.
The script performs the following tasks:
1. Parses command-line arguments to configure the extraction process.
2. Loads the depot manifest and decrypts filenames if necessary.
3. Handles backup chunkstores if provided.
4. Matches files to be extracted based on provided patterns.
5. Processes chunks, decrypting and decompressing them as needed.
6. Validates the SHA-1 checksum of the output files if requested.
7. Writes metadata to track the progress of the extraction process.
8. Uses a ThreadPoolExecutor to process chunks in parallel, improving performance.
9. Uses a PriorityQueue to ensure chunks are written in the correct order.
The try loop within the ThreadPoolExecutor block is responsible for:
- Submitting tasks to process each chunk in parallel.
- Collecting the results of the processed chunks.
- Writing the decompressed chunks to the output file in the correct order.
- Handling retries in case of PermissionError during file operations.
"""
from argparse import ArgumentParser
from binascii import hexlify
from datetime import datetime
from fnmatch import fnmatch
from glob import glob
from hashlib import sha1
from io import BytesIO
from os import makedirs, remove
from os.path import dirname, exists, join
from pathlib import Path
from struct import unpack
from sys import argv
from zipfile import ZipFile
import lzma
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import logging
import time
from queue import PriorityQueue

_LOG = logging.getLogger("DepotExtractor")

if __name__ == "__main__": # exit before we import our shit if the args are wrong
    parser = ArgumentParser(description='Extract downloaded depots.')
    parser.add_argument('depotid', type=int)
    parser.add_argument('manifestid', type=int)
    parser.add_argument('depotkey', type=str, nargs='?')
    parser.add_argument('-d', dest="dry_run", help="dry run: verify chunks without extracting", action="store_true")
    parser.add_argument('-f', dest="files", help="List files to extract (can be used multiple times); if ommitted, all files will be extracted. Glob matching supported.", action="append")
    parser.add_argument('-b', dest="backup", help="Path to a .csd backup file to extract (the manifest must also be present in the depots folder)", nargs='?')
    parser.add_argument('--dest', help="directory to place extracted files in", type=str, default="extract")
    parser.add_argument('--validate', help="Validate the SHA-1 checksum of the output files", action="store_true")
    parser.add_argument('--max-threads', help="Maximum number of threads to use for extraction", dest="max_threads", type=int, default=4)
    log_group = parser.add_mutually_exclusive_group()
    log_group.add_argument("--debug", help="Enable debug logging", action="store_true")
    log_group.add_argument("--info", help="Enable info logging", action="store_true")
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    elif args.info:
        logging.basicConfig(level=logging.INFO)

from steam.core.manifest import DepotManifest
from steam.core.crypto import symmetric_decrypt
from chunkstore import Chunkstore

if __name__ == "__main__":
    path = "./depots/%s" % args.depotid
    manifest_path = join(path, "manifest")
    chunk_path = join(path, "chunk/")
    keyfile = "./depots/%s/%s.depotkey" % (args.depotid, args.depotid)
    manifest = None
    badfiles = []
    with open(join(manifest_path, "%s.manif5" % (args.manifestid)), "rb") as f:
        manifest = DepotManifest(f.read())
    if args.depotkey:
        args.depotkey = bytes.fromhex(args.depotkey)
        if manifest.filenames_encrypted:
            manifest.decrypt_filenames(args.depotkey)
    elif manifest.filenames_encrypted:
            ## Using No-Intro's DepotKey format, which is
            ## a 32-byte/256-bit binary file.
            ## Examples require login to No-Intro to view.
            if exists(keyfile):
                with open(keyfile, "rb") as f:
                    args.depotkey = f.read()
                    manifest.decrypt_filenames(args.depotkey)
            ## If depotkey is not found, locate depot_keys.txt
            ## and check if key is located in there.
            elif exists("./depot_keys.txt"):
                with open("./depot_keys.txt", "r", encoding="utf-8") as f:
                    for line in f.read().split("\n"):
                        line = line.split("\t")
                        try:
                            if int(line[0]) == args.depotid:
                                args.depotkey = bytes.fromhex(line[2])
                                manifest.decrypt_filenames(args.depotkey)
                                break
                        except ValueError:
                            pass
                    if not args.depotkey:
                        print("ERROR: manifest has encrypted filenames, but no depot key was specified and no key for this depot exists in depot_keys.txt")
                        exit(1)
            else:
                print("ERROR: manifest has encrypted filenames, but no depot key was specified and no depot_keys.txt exists")
                exit(1)

    chunkstores = {}
    chunks_by_store = {}
    if args.backup:
        for csm in glob(args.backup.replace("_1.csm","").replace("_1.csd","") + "_*.csm"):
            chunkstore = Chunkstore(csm)
            chunkstore.unpack()
            for chunk, _ in chunkstore.chunks.items():
                chunks_by_store[chunk] = csm
            chunkstores[csm] = chunkstore

    def is_match(file):
        for pattern in args.files:
            if fnmatch(file.filename, pattern): return True
        return False

    def process_chunk(chunk, chunk_path, args, file, chunkstores, chunks_by_store, badfiles):
        chunkhex = hexlify(chunk.sha).decode()
        decrypted = None
        try:
            if args.backup:
                chunk_data = None
                is_encrypted = False
                try:
                    chunkstore = chunkstores[chunks_by_store[chunk.sha]]
                    chunk_data = chunkstore.get_chunk(chunk.sha)
                    is_encrypted = chunkstore.is_encrypted
                except:
                    print("missing chunk " + chunkhex)
                    badfiles.append(chunkhex)
                    return None
                if is_encrypted:
                    if args.depotkey:
                        decrypted = symmetric_decrypt(chunk_data, args.depotkey)
                    else:
                        print("ERROR: chunk %s is encrypted, but no depot key was specified" % chunkhex)
                        return None
                else:
                    decrypted = chunk_data
            else:
                chunk_file_path = chunk_path + chunkhex
                decrypted_chunk_file_path = chunk_file_path + "_decrypted"
                _LOG.info(f"Checking for chunk file: {chunk_file_path}")
                _LOG.info(f"Checking for decrypted chunk file: {decrypted_chunk_file_path}")
                if exists(chunk_file_path):
                    with open(chunk_file_path, "rb") as chunkfile:
                        if args.depotkey:
                            decrypted = symmetric_decrypt(chunkfile.read(), args.depotkey)
                        else:
                            print("ERROR: chunk %s is encrypted, but no depot key was specified" % chunkhex)
                            return None
                elif exists(decrypted_chunk_file_path):
                    with open(decrypted_chunk_file_path, "rb") as chunkfile:
                        decrypted = chunkfile.read()
                else:
                    print("missing chunk " + chunkhex)
                    badfiles.append(chunkhex)
                    return None

            decompressed = None
            if decrypted[:2] == b'VZ':  # LZMA
                if args.dry_run:
                    print("Testing", file.filename, "(LZMA) from chunk", chunkhex)
                # else:
                #     print("Extracting", file.filename, "(LZMA) from chunk", chunkhex)
                decompressed = lzma.LZMADecompressor(lzma.FORMAT_RAW, filters=[lzma._decode_filter_properties(lzma.FILTER_LZMA1, decrypted[7:12])]).decompress(decrypted[12:-9])[:chunk.cb_original]
            elif decrypted[:2] == b'PK':  # Zip
                if args.dry_run:
                    print("Testing", file.filename, "(Zip) from chunk", chunkhex)
                # else:
                #     print("Extracting", file.filename, "(Zip) from chunk", chunkhex)
                zipfile = ZipFile(BytesIO(decrypted))
                decompressed = zipfile.read(zipfile.filelist[0])
            else:
                print("ERROR: unknown archive type", decrypted[:2].decode())
                badfiles.append(chunkhex)
                return None

            sha = sha1(decompressed)
            if sha.digest() != chunk.sha:
                print("ERROR: sha1 checksum mismatch (expected %s, got %s)" % (hexlify(chunk.sha).decode(), sha.hexdigest()))
                badfiles.append(chunkhex)
                return None

            return (chunk.offset, decompressed, chunkhex)
        except Exception as e:
            print(f"Error processing chunk {chunkhex}: {e}")
            return None

    def write_metadata(metadata_path, metadata):
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=4)

    def read_metadata(metadata_path):
        if exists(metadata_path):
            with open(metadata_path, "r") as f:
                return json.load(f)
        return {}

    def validate_file(file_path, expected_sha1):
        sha1_hash = sha1()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha1_hash.update(byte_block)
        calculated_sha1 = sha1_hash.hexdigest()
        return calculated_sha1 == expected_sha1

    def preset_file_size(file_path, size):
        retries = 5
        for attempt in range(retries):
            try:
                with open(file_path, "wb") as f:
                    f.truncate(size)
                break
            except PermissionError as e:
                if attempt < retries - 1:
                    time.sleep(1)  # Wait for 1 second before retrying
                else:
                    raise e

    if __name__ == "__main__":
        output_dir_parent = join(args.dest, str(args.depotid))
        output_dir = join(output_dir_parent, str(args.manifestid))
        if not args.dry_run:
            makedirs(output_dir, exist_ok=True)
        metadata_path = join(output_dir_parent, "metadata.json")
        metadata = read_metadata(metadata_path)

        try:
            # First, create all directories
            for file in manifest.iter_files():
                if file.flags == 64:
                    dir_path = join(output_dir, file.filename)
                    if not exists(dir_path):
                        makedirs(dir_path, exist_ok=True)

            # Then, process all files
            for file in manifest.iter_files():
                if file.flags == 64:
                    continue  # Skip directories
                if args.files and not is_match(file): continue
                target = join(output_dir, dirname(file.filename))
                final_file_path = join(output_dir, file.filename)
                incomplete_file_path = join(output_dir, file.filename + ".incomplete")
                file_metadata = metadata.get(file.filename, {
                    "total_chunks": len(file.chunks),
                    "processed_chunks": []
                })
                processed_chunks = set(file_metadata["processed_chunks"])

                # Check if the file or its incomplete version exists
                if not exists(final_file_path) and not exists(incomplete_file_path):
                    # If neither exists but the file is marked as processed in metadata, clear the processed chunks
                    if processed_chunks:
                        print(f"File {file.filename} is missing. Clearing processed chunks and starting over.")
                        processed_chunks.clear()
                        file_metadata["processed_chunks"] = list(processed_chunks)
                        metadata[file.filename] = file_metadata
                        write_metadata(metadata_path, metadata)

                # Skip processing if the final file already exists and is valid
                if not args.dry_run and exists(final_file_path):
                    if args.validate:
                        expected_sha1 = hexlify(file.sha_content).decode()
                        if validate_file(final_file_path, expected_sha1):
                            print(f"File {file.filename} already exists and is \033[92m\033[1mvalid\033[0m. Skipping...")
                            continue
                        else:
                            print(f"File {file.filename} already exists but is \033[91m\033[1minvalid\033[0m. Reprocessing...")
                    else:
                        print(f"File {file.filename} already exists. Skipping...")
                        continue

                if not args.dry_run:
                    try:
                        makedirs(target, exist_ok=True)
                    except FileExistsError:
                        remove(target)
                        makedirs(target, exist_ok=True)
                    except NotADirectoryError:
                        # bruh
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

                    # Preset the file size before processing chunks
                    preset_file_size(incomplete_file_path, file.size)

                try:
                    with ThreadPoolExecutor(max_workers=args.max_threads) as executor:  # Specify the number of threads here
                        futures = [executor.submit(process_chunk, chunk, chunk_path, args, file, chunkstores, chunks_by_store, badfiles) for chunk in sorted(file.chunks, key=lambda chunk: chunk.offset) if hexlify(chunk.sha).decode() not in processed_chunks]
                        pq = PriorityQueue()
                        for future in as_completed(futures):
                            result = future.result()
                            if result is not None:
                                pq.put(result)
                        if not args.dry_run:
                            retries = 5
                            for attempt in range(retries):
                                try:
                                    with open(incomplete_file_path, "r+b") as f:
                                        while not pq.empty():
                                            offset, decompressed, chunkhex = pq.get()
                                            f.seek(offset)
                                            f.write(decompressed)
                                            processed_chunks.add(chunkhex)
                                            # Update metadata after each chunk is processed
                                            file_metadata["processed_chunks"] = list(processed_chunks)
                                            metadata[file.filename] = file_metadata
                                            write_metadata(metadata_path, metadata)
                                            _LOG.info(f"Extracted {file.filename} from chunk {chunkhex}")
                                    break
                                except PermissionError as e:
                                    if attempt < retries - 1:
                                        time.sleep(1)  # Wait for 1 second before retrying
                                    else:
                                        raise e
                            if len(processed_chunks) == file_metadata["total_chunks"]:
                                Path(incomplete_file_path).rename(final_file_path)
                                if args.validate and file.flags != 64:
                                    expected_sha1 = hexlify(file.sha_content).decode()
                                    if validate_file(final_file_path, expected_sha1):
                                        print(f"Validation \033[92m\033[1msuccessful\033[0m for {file.filename}")
                                    else:
                                        print(f"Validation \033[91m\033[1mfailed\033[0m for {file.filename}")
                                        corrupted_file_path = final_file_path + ".corrupted"
                                        Path(final_file_path).rename(corrupted_file_path)
                                        print(f"Renamed {final_file_path} to {corrupted_file_path}")
                            else:
                                metadata[file.filename] = file_metadata
                                write_metadata(metadata_path, metadata)
                except IsADirectoryError:
                    pass

        except KeyboardInterrupt:
            print("Process interrupted. Saving metadata...")
            write_metadata(metadata_path, metadata)
            exit(1)
        except Exception as e:
            print(f"An error occurred: {e}")
            write_metadata(metadata_path, metadata)
            exit(1)

        if badfiles:
            print("ERROR: the following files are missing or corrupt:")
            for file in badfiles:
                print(file)
            exit(1)