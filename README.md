# Bring Your Own Patches - IDPK Builder

`byop` is a command line tool to create an Infrastructure DPK (Infra-DPK) package for use with the PeopleTools DPK. `byop` takes a list of patches (in YAML format) and will download and the patches you specify. The files will be added to the correct folder and at the end a new `psft_patches.yaml`. The new YAML file and downloads are ready to applied to your system.

This tool is not intended to replace the Oracle-delivered Infra-DPK. The intent is to make it easier to apply CPU patches to PeopleSoft systems easier by leveraging the DPK toolset. The Infra-DPK package can sometimes take a few weeks to be available, but most of the individual patches are available right way. `byop` can let you download the patches that are avaiable and apply them to your system quickly.

# Installing

## Git
```
git clone https://github.com/psadmin-io/byop.git
cd byop
python3 -m pip install .
```

# Building an Infra-DPK Package

```bash
$ byop config

Mos username: dan@psadmin.io
Mos password: 
[INFO ]  Configuration save to config.json

byop build

[INFO ]  Authenticating with MOS
[INFO ]   - MOS Login was Successful
[INFO ]  Downloading 5 patches for Weblogic
[INFO ]  Downloading 1 patches for Weblogic OPatch Patches
[INFO ]  Downloading 1 patches for Tuxedo
[INFO ]  Downloading 1 patches for Oracle Client
[INFO ]  Downloading 1 patches for Oracle Client OPatch Patches
[INFO ]  Downloading 1 patches for JDK
[INFO ]   - Converting JDK to DPK format
---------------------------------------
get_mos_authentication       : 00:00:04
weblogic patches             : 00:00:14
weblogic opatch patches      : 00:00:05
tuxedo patches               : 00:00:02
oracleclient patches         : 00:01:04
oracleclient opatch patches  : 00:00:07
jdk patches                  : 00:00:40
---------------------------------------
TOTAL TIME                   : 00:02:16
---------------------------------------
```

`byop` will take an input YAML file (`byop.yaml` is the default) and will download the patches listed in the file, and create a `psft_patches.yaml` file.

You can use different YAML file names if you want to version each release.

```bash
byop build --src-yaml 22q4.yaml --tgt-yaml psft_patces_22q4.yaml
```

There is a debug output mode that is enabled with the `--verbose` flag. You can use the `--quiet` flag to not print the timing output.

## Status 

`byop` tracks with patches were downloaded so you can save bandwith and time by not redownloading files. In the `tmp` folder, the patch status is tracked in the JSON file `patch_status_file`. You can reset a patch to `false` and `byop` will download the patch again. If you want to redownload all the patches and ignore the status, you can pass the `--redownload` flag.

```bash
byop build --help
Usage: byop build [OPTIONS]

  Download and create an Infra-DPK package

Options:
  -s, --src-yaml TEXT  Input YAML with IDPK Patches  [default: byop.yaml]
  -t, --tgt-yaml TEXT  Output YAML to use with DPK  [default:
                       psft_patches.yaml]
  --redownload         Ignore patch status - force all patches to be
                       redownloaded.
  --quiet              Don't print timing output
  --verbose            Enable debug logging
  --help               Show this message and exit.
```

## Cleanup

When are you done building your Infra-DPK bundle, or if you want to start over, you can run the `cleanup` command to remove patches and temporary files.

```bash
byop cleanup --help
Usage: byop cleanup [OPTIONS]

  Remove files from the tmp and cpu_archives directories and remove PT-INFRA
  zip files.

Options:
  --tmp            Delete tmp files
  --only-tmp       Only delete tmp files
  --yaml           Include psft_patches.yaml in cleanup
  --tgt-yaml TEXT  Target YAML file to delete. Default is psft_patches.yaml.
  --zip            Include PT-INFRA*.zip in cleanup
  --zip-dir TEXT   Output directory for PT-INFRA zip file
  --only-zip       Only delete PT-INFRA zip file
  --quiet          Don't print timing output
  --verbose        Enable debug logging
  --help           Show this message and exit.
```

## Create Infra-DPK Zip File



```bash
byop zip --help
Usage: byop zip [OPTIONS]

  Package Infra-DPK files into a .zip file

Options:
  --src-yaml TEXT  Input YAML with IDPK Patches  [default: byop.yaml]
  --zip-dir TEXT   Output directory for PT-INFRA zip file
  --quiet          Don't print timing output
  --verbose        Enable debug logging
  --help           Show this message and exit.
```


## Debugging



### MOS Simple Search

To troubleshoot download issues, start with the MOS Simple Search page to see if the patch is available: https://updates.oracle.com/Orion/SimpleSearch/process_form

# Setting up for development
```
python -m pip install virtualenv --user

cd byop
python -m virtualenv -p python3 venv
## Linux/macOS
. venv/bin/activate
## Windows
. venv/scripts/activate

python -m pip install --editable .
```



