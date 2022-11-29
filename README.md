# Bring Your Own Patches - IDPK Builder

`byop` is a command line tool to create an Infrastructure DPK (Infra-DPK) package for use with the PeopleTools DPK. `byop` takes a list of patches (in YAML format) and will download and the patches you specify. The files will be added to the correct folder and at the end a new `psft_patches.yaml`. The new YAML file and downloads are ready to applied to your system.

This tool is not intended to replace the Oracle-delivered Infra-DPK. The intent is to make it easier to apply CPU patches to PeopleSoft systems easier by leveraging the DPK toolset. The Infra-DPK package can sometimes take a few weeks to be available, but most of the individual patches are available right way. `byop` can let you download the patches that are avaiable and apply them to your system quickly.


# Installing
```
cd byop
pip install .
```

# Setting up for development
```
pip install virtualenv 

cd byop
virtualenv -p python3 venv
. venv/bin/activate

pip install --editable .
```