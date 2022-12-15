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
```

`byop` will take an input YAML file (`byop.yaml` is the default) and will download the patches listed in the file, and create a `psft_patches.yaml` file.

You can use different YAML file names if you want to version each release.

```bash
byop build --src-yaml 22q4.yaml --tgt-yaml psft_patces_22q4.yaml
```

There is a debug output mode that is enabled with the `--verbose` flag.





# Setting up for development
```
pip install virtualenv 

cd byop
virtualenv -p python3 venv
. venv/bin/activate

pip install --editable .
```

# MOS Simple Search

To troubleshoot download issues, start with the MOS Simple Search page to see if the patch is available: https://updates.oracle.com/Orion/SimpleSearch/process_form

