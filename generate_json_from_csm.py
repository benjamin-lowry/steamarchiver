import os
import json
from struct import iter_unpack

class CSMReader:
    def __init__(self, filename):
        self.filename = filename
        self.chunks = {}
        self.depot = None
        self.is_encrypted = None
        self._load_csm_file()

    def _load_csm_file(self):
        with open(self.filename, "rb") as csmfile:
            csm = csmfile.read()
            if csm[:4] != b"SCFS":
                print("Not a CSM file: " + self.filename)
                return False
            self.depot = int.from_bytes(csm[0xc:0x10], byteorder='little', signed=False)
            self.is_encrypted = (csm[0x8:0xa] == b'\x03\x00')
            self._unpack(csm[0x14:])

    def _unpack(self, csm_data):
        for sha, offset, _, length in iter_unpack("<20s Q L L", csm_data):
            self.chunks[sha] = (offset, length)

    def to_dict(self):
        return {
            "depot": self.depot,
            "is_encrypted": self.is_encrypted,
            "chunks": [
                {
                    "sha": sha.hex(),
                    "offset": offset,
                    "length": length
                }
                for sha, (offset, length) in self.chunks.items()
            ]
        }

def generate_json_from_csm(directory):
    for filename in os.listdir(directory):
        if filename.endswith(".csm"):
            csm_reader = CSMReader(os.path.join(directory, filename))
            json_output = csm_reader.to_dict()
            json_filename = os.path.join(directory, f"{os.path.splitext(filename)[0]}.json")
            with open(json_filename, "w") as json_file:
                json.dump(json_output, json_file, indent=4)
            print(f"Generated JSON for {filename}: {json_filename}")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate JSON outputs from CSM files in a specified directory.")
    parser.add_argument("directory", type=str, help="Directory containing CSM files.")
    args = parser.parse_args()

    generate_json_from_csm(args.directory)