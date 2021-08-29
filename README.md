# steamarchiver

A set of Python scripts to download Steam depots in SteamPipe CDN format and
extract their content, for future preservation.

## Usage

First install the requirements:

``pip3 install -r requirements.txt``

There are three scripts currently.

- ``depot_archiver.py`` downloads depots (the logical groupings of game content
  files Steam delivers). You can give it an appid, in which case it'll download
  the latest depots for that app, or you can give it a specific appid, depotid,
  and manifest number (manifests are specific versions of depots.) It will
  download the manifest, appinfo, and encrypted depot chunks. **You don't need
  to own a game to archive its depots; you only need ownership to get the key
  needed to actually extract files from the encrypted chunks.**
- ``get_depot_keys.py`` logs into a Steam account and dumps all the depot keys
  it has access to, which can be used to decrypt downloaded depots. To get the
  key for a depot, your account must own a package that includes access to the
  depot, and it must also own a package that includes an app which specifies the
  depot should be installed; you cannot get keys for depots you have access to
  that aren't included in any released apps, since that's how Steam prevents you
  from decrypting preloaded game content. Keys will be saved to depot_keys.txt
- ``depot_extractor.py`` extracts downloaded depots. It requires the key but can
  work completely offline.

For help finding appids, depotids, and manifests, check out
https://steamdb.info

## Example

Get all the depot keys for your account (interactive login prompt will be
shown):

    python3 get_depot_keys.py

Download all the depots for Team Fortress 2:

    python3 depot_archiver.py 440

Download the Team Fortress 2 Linux client binaries that were released at
2021-06-22 20:13:56:

    python3 depot_archiver.py 440 232253 3977101045377481242

Extract those binaries:

    python3 depot_extractor.py 232253 3977101045377481242 bdbeae4f56fa865d8df2f76623d3346fcd7e56df6dee13b0f23e4a0fe160a446

(Note: the key for the above command was found in depot_keys.txt, in this line:)

    232253		bdbeae4f56fa865d8df2f76623d3346fcd7e56df6dee13b0f23e4a0fe160a446	TF2 Linux client

## License

   Copyright 2021 Benjamin Lowry

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
