import os
import py
import re
import sys
import json
import yaml
import glob
import logging
import datetime
import click
import shutil
import requests
import tarfile
import zipfile
import cryptocode
from requests.auth import HTTPBasicAuth

# Config Object
class Config(dict):
    def __init__(self, *args, **kwargs):
        self.config = py.path.local().join('config.json')
        super(Config, self).__init__(*args, **kwargs)

    def load(self):
        """load a JSON config file from disk"""
        try:
            self.update(json.loads(self.config.read()))
        except py.error.ENOENT:
            pass

    def save(self):
        self.config.ensure()
        with self.config.open('w') as f:
            f.write(json.dumps(self, indent=2))

# Common Command ptions
def verbose_option(f):
    def callback(ctx, param, value):
        state = ctx.ensure_object(Config)
        state.verbose = value
        return value
    return click.option('--verbose',
                        default=False,
                        is_flag=True,
                        help='Enable debug logging',
                        callback=callback)(f)

def quiet_option(f):
    def callback(ctx, param, value):
        state = ctx.ensure_object(Config)
        state.verbose = value
        return value
    return click.option('--quiet', 
                        default=False, 
                        is_flag=True, 
                        help="Don't print timing output",
                        callback=callback)(f)

def common_options(f):
    f = verbose_option(f)
    f = quiet_option(f)
    return f

# Initialization
pass_config = click.make_pass_decorator(Config, ensure=True)
this = sys.modules[__name__]
this.config = None
this.timings = None
this.codes = {}

# Constants
PEOPLETOOLS = "peopletools"
JDK = "jdk"
JDK_PATCHES = "jdk_patches"
JDK_PATCHES_VERSION = "jdk_patches_version"
ORACLECLIENT_OPATCH = "oracleclient_opatch"
ORACLECLIENT_OPATCH_PATCHES = "oracleclient_opatch_patches"
ORACLECLIENT = "oracleclient"
ORACLECLIENT_PATCHES = "oracleclient_patches"
ORACLECLIENT_PATCHES_VERSION = "oracleclient_patches_version"
TUXEDO = "tuxedo"
TUXEDO_PATCHES = "tuxedo_patches"
TUXEDO_PATCHES_VERSION = "tuxedo_patches_version"
WEBLOGIC_OPATCH = "weblogic_opatch"
WEBLOGIC_OPATCH_PATCHES = "weblogic_opatch_patches"
WEBLOGIC = "weblogic"
WEBLOGIC_PATCHES = "weblogic_patches"
WEBLOGIC_PATCHES_VERSION = "weblogic_patches_version"
ARCHIVE = 'archive_dir'
TEMP = 'tmp_dir'
STATUS = 'patch_status_file'
OUTPUT = 'zip_dir'

# ###### #
# cli    #
# ###### #
@click.group(no_args_is_help=True)
@pass_config
def cli(config):
    """Bring Your Own Patches - Infrastructure DPK Builder"""

    # Load Config from file
    config.load()
    this.config = config

    # Timings setup 
    this.total_time_key = 'TOTAL TIME'
    this.timings_printed = False

    if not config.get(OUTPUT):
        this.config[OUTPUT] = os.path.join(os.getcwd(), 'output')
    if not config.get(ARCHIVE):
        this.config[ARCHIVE] = os.path.join(config.get(OUTPUT), 'cpu_archives')
    if not config.get(TEMP):
        this.config[TEMP] = os.path.join(os.getcwd(), 'tmp')
    if not config.get(STATUS):
        this.config[STATUS] = os.path.join(this.config[TEMP], STATUS)

    pass

# ###### #
# config #
# ###### #
@cli.command()
@click.option('-u', '--mos-username',
              help='My Oracle Support Username',
              prompt=True)
@click.option('-p', '--mos-password',
              help='My Oracle Support Password',
              prompt=True, hide_input=True, confirmation_prompt=True)
@pass_config
def config(config, mos_username, mos_password):
    """Build the config.json"""
    setup_logging()

    encoded = cryptocode.encrypt(mos_password,"NIswEgoOj39wpzJcqocQ8mw4iMkqtS")
    config["mos_username"] = mos_username
    config["mos_password"] = encoded
    config.save()
    logging.info("Configuration save to config.json")
    __create_patch_status()

# ####### #
# cleanup #
# ####### #
@cli.command()
@click.option('--tmp',
              is_flag=True,
              default=True,
              help="Delete tmp files")
@click.option('--only-tmp',
              is_flag=True,
              default=False,
              help="Only delete tmp files")
@click.option('--yaml',
              is_flag=True,
              default=False,
              help="Include psft_patches.yaml in cleanup")
@click.option('--tgt-yaml', 
              help="Target YAML file to delete. Default is psft_patches.yaml.",
              default='psft_patches.yaml')
@click.option('--zip',
              is_flag=True,
              default=True,
              help="Include PT-INFRA*.zip in cleanup")
@click.option('--zip-dir',
              help="Output directory for PT-INFRA zip file" )
@click.option('--only-zip',
              is_flag=True,
              default=False,
              help="Only delete PT-INFRA zip file")
@pass_config
@common_options
def cleanup(config, tmp, only_tmp, yaml, tgt_yaml, zip, zip_dir, only_zip, verbose, quiet):
    """Remove files from the tmp and cpu_archives directories and remove PT-INFRA zip files."""
    this.config['verbose'] = verbose
    this.config['quiet'] = quiet
    setup_logging()

    if not only_zip and not only_tmp:
        # cpu_archives
        files = glob.glob(config.get(ARCHIVE) + "/*/*", recursive=True)
        if files:
            try:
                shutil.rmtree(config.get(ARCHIVE))
                logging.info("Removed cpu_archive files")
            except OSError as e:
                logging.error("Error: %s : %s" % (files, e.strerror))
        else:
            logging.info("No patches to cleanup")
        
        # YAML files
        if yaml:
            yamlfile = os.path.join(this.config.get(OUTPUT), tgt_yaml)
            if os.path.exists(yamlfile):
                try:
                    os.remove(yamlfile)
                    logging.info("Removed " + str(yamlfile))
                except OSError as e:
                    logging.error("Error: %s : %s" % (yamlfile, e.strerror))
            else:
                logging.info("No " + tgt_yaml + " file to cleanup")

    if (tmp or only_tmp) and not only_zip:
        # tmp
        files = glob.glob(config.get(TEMP) + "/*", recursive=True)
        if files:
            try:
                shutil.rmtree(config.get(TEMP))
                logging.info("Removed tmp files")
            except OSError as e:
                logging.error("Error: %s : %s" % (files, e.strerror))
        else:
            logging.info("No temporary files to cleanup")

    # PT-INFRA zip file
    if zip or only_zip:
        if not zip_dir:
            zip_dir = this.config[OUTPUT]
        files = glob.glob(os.path.join(zip_dir, "PT-INFRA*.zip"))
        logging.debug("Zip files to remove: " + str(files))
        if files:
            for file in files:
                try:
                    os.remove(file)
                    logging.info("Removed " + file)
                except OSError as e:
                    logging.error("Error: %s : %s" % (file, e.strerror))
        else:
            logging.info("No PT-INFRA zip to cleanup")

# ##### #
# build #
# ##### #
@cli.command()
@click.option('-s', '--src-yaml', 
              default="byop.yaml", 
              show_default=True,
              help="Input YAML with IDPK Patches")
@click.option('-t', '--tgt-yaml', 
              default="psft_patches.yaml", 
              show_default=True, 
              help="Output YAML to use with DPK")
@click.option('--redownload',
              default=False,
              is_flag=True,
              help="Ignore patch status - force all patches to be redownloaded.")
@common_options
@pass_config
def build(config, src_yaml, tgt_yaml, redownload, verbose, quiet):
    """Download and create an Infra-DPK package"""

    this.config['verbose'] = verbose
    this.config['quiet'] = quiet
    setup_logging()
    
    this.config['redownload'] = redownload
    if not config.get('download_threads'):
        this.config['download_threads'] = 2
    this.config['src_yaml'] = src_yaml
    this.config['tgt_yaml'] = os.path.join(this.config[OUTPUT], tgt_yaml)
    logging.debug("Source YAML: " + this.config['tgt_yaml'])
    logging.debug("Target YAML: " + this.config['tgt_yaml'])
    logging.debug(this.config['mos_username'])

    if not os.path.exists(src_yaml):
        logging.info("Source YAML File not found: " + src_yaml)
        exit(2)

    init_timings()
    build_directories()
    download_patches()
    print_timings()
    pass

# ### #
# zip #
# ### #
@cli.command()
@click.option('--src-yaml', 
              default="byop.yaml", 
              show_default=True,
              help="Input YAML with IDPK Patches")
@click.option('-t', '--tgt-yaml', 
              default="psft_patches.yaml", 
              show_default=True, 
              help="Output YAML to use with DPK")
@click.option('--zip-dir',
              help="Output directory for PT-INFRA zip file" )
@common_options
@pass_config
def zip(config, src_yaml, tgt_yaml, zip_dir, verbose, quiet):
    """Package Infra-DPK files into a .zip file"""

    this.config['verbose'] = verbose
    this.config['quiet'] = quiet
    this.config['src_yaml'] = src_yaml
    this.config['tgt_yaml'] = os.path.join(this.config[OUTPUT], tgt_yaml)
    if zip_dir:
        archive_dir = zip_dir
    else:
        archive_dir = os.path.join(this.config[OUTPUT])
    setup_logging()
    init_timings()

    create_zip_file(archive_dir, tgt_yaml)

    print_timings()

# ################# #
# Library Functions #
# ################# #
def build_directories():
    try:
        os.makedirs(this.config[OUTPUT], exist_ok = True)
    except OSError as error:
        logging.error("Directory '%s' can not be created" % this.config[OUTPUT])
    try:
        os.makedirs(this.config[ARCHIVE], exist_ok = True)
    except OSError as error:
        logging.error("Directory '%s' can not be created" % this.config[ARCHIVE])


    try:
        os.makedirs(os.path.join(this.config[ARCHIVE], WEBLOGIC_PATCHES), exist_ok = True)
    except OSError as error:
        logging.error("Directory '%s' can not be created" % os.path.join(this.config[ARCHIVE], WEBLOGIC_PATCHES))
    try:
        os.makedirs(os.path.join(this.config[ARCHIVE], WEBLOGIC_OPATCH_PATCHES), exist_ok = True)
    except OSError as error:
        logging.error("Directory '%s' can not be created" % os.path.join(this.config[ARCHIVE], WEBLOGIC_OPATCH_PATCHES))
    try:
        os.makedirs(os.path.join(this.config[ARCHIVE], TUXEDO_PATCHES), exist_ok = True)
    except OSError as error:
        logging.error("Directory '%s' can not be created" % os.path.join(this.config[ARCHIVE], TUXEDO_PATCHES))
    try:
        os.makedirs(os.path.join(this.config[ARCHIVE], ORACLECLIENT_PATCHES), exist_ok = True)
    except OSError as error:
        logging.error("Directory '%s' can not be created" % os.path.join(this.config[ARCHIVE], ORACLECLIENT_PATCHES))
    try:
        os.makedirs(os.path.join(this.config[ARCHIVE], ORACLECLIENT_OPATCH_PATCHES), exist_ok = True)
    except OSError as error:
        logging.error("Directory '%s' can not be created" % os.path.join(this.config[ARCHIVE], ORACLECLIENT_OPATCH_PATCHES))
    try:
        os.makedirs(os.path.join(this.config[ARCHIVE], JDK_PATCHES), exist_ok = True)
    except OSError as error:
        logging.error("Directory '%s' can not be created" % os.path.join(this.config[ARCHIVE], JDK_PATCHES))

    try:
        os.makedirs(os.path.join(this.config[TEMP]), exist_ok = True)
    except OSError as error:
        logging.error("Directory '%s' can not be created" % os.path.join(this.config[TEMP]))

def download_patches():
    yml, ptversion, platform = __validate_input()

    # Get MOS Session for downloads
    session = __get_mos_authentication()

    # Download patches
    if yml.get(WEBLOGIC):
        release = this.codes[PEOPLETOOLS][str(ptversion)][WEBLOGIC]
        get_weblogic_patches(session, yml, WEBLOGIC, platform, release)
    else:
        logging.info("No Weblogic Patches")

    if yml.get(WEBLOGIC_OPATCH):
        release = this.codes[PEOPLETOOLS][str(ptversion)][WEBLOGIC_OPATCH]
        get_weblogic_opatch_patches(session, yml, WEBLOGIC_OPATCH, platform, release)
    else:
        logging.info("No Weblogic OPatch Patches")

    if yml.get(TUXEDO):
        release = this.codes[PEOPLETOOLS][str(ptversion)][TUXEDO]
        get_tuxedo_patches(session, yml, TUXEDO, platform, release)
    else:
        logging.info("No Tuxedo Patches")

    if yml.get(ORACLECLIENT):
        release = this.codes[PEOPLETOOLS][str(ptversion)][ORACLECLIENT]
        get_oracleclient_patches(session, yml, ORACLECLIENT, platform, release)
    else:
        logging.info("No Oracle Client Patches")

    if yml.get(ORACLECLIENT_OPATCH):
        release = this.codes[PEOPLETOOLS][str(ptversion)][ORACLECLIENT_OPATCH]
        get_oracleclient_opatch_patches(session, yml, ORACLECLIENT_OPATCH, platform, release)
    else:
        logging.info("No Oracle Client OPatch Patches")
    
    if yml.get(JDK):
        release = this.codes[PEOPLETOOLS][str(ptversion)][JDK]
        get_jdk_patches(session, yml, JDK, platform, release)
    else:
        logging.info("No JDK Patches")

def create_zip_file(archive_dir, tgt_yaml):
    timing_key = "create zip file"
    start_timing(timing_key)

    yml, ptversion, platform = __validate_input()
    regex = r"(\d{1})\.?(\d{2})"
    pattern = "\\1.\\2"
    ptversion = re.sub(regex, pattern, ptversion)

    platform = yml['platform']

    if platform == 'linux':
        platform_short = 'LNX'
    elif platform == 'windows':
        platform_short = 'WIN'
    now = datetime.datetime.now()
    date = now.strftime("%y%m%d")

    zipno = '1'
    zipname = 'PT-INFRA-DPK-' + platform_short + '-' + ptversion + '-' + date + '_' + zipno + 'of2.zip'
    logging.debug("Infra-DPK zip file name: " + zipname)
    zipfolders = [JDK_PATCHES, TUXEDO_PATCHES, WEBLOGIC_PATCHES, WEBLOGIC_OPATCH_PATCHES]
    __zipdirectory(zipname, zipfolders)
    logging.info("Created " + zipname)
    logging.debug("Adding psft_patches.yaml to zip 1")
    __zipyaml(zipname, tgt_yaml)

    zipno = '2'
    zipname = 'PT-INFRA-DPK-' + platform_short + '-' + ptversion + '-' + date + '_' + zipno + 'of2.zip'
    logging.debug("Infra-DPK zip file name: " + zipname)
    zipfolders = [ORACLECLIENT_PATCHES, ORACLECLIENT_OPATCH_PATCHES]
    __zipdirectory(zipname, zipfolders)
    logging.info("Created " + zipname)
    
    end_timing(timing_key)

def get_weblogic_patches(session, yml, section, platform, release):
    timing_key = "weblogic patches"
    start_timing(timing_key)
    
    weblogic_patches = {}
    weblogic_patches_version = {}

    logging.info("Downloading " + str(len(yml[section])) + " patches for Weblogic")
    downloaded = False
    for i, patch in enumerate(yml[section], start=1):
        file_name = __get_patch(session, patch, platform, release, WEBLOGIC_PATCHES)
        if file_name:
            downloaded = True
            weblogic_patches_version["patch" + str(i)] = str(patch)
            weblogic_patches["patch" + str(i)] = '%{hiera("peoplesoft_base")}/dpk/cpu_archives/' + WEBLOGIC_PATCHES + '/' + file_name

    if downloaded:
        logging.debug(WEBLOGIC_PATCHES_VERSION + ": ")
        logging.debug(yaml.dump(weblogic_patches_version))
        __write_to_yaml(weblogic_patches_version, WEBLOGIC_PATCHES_VERSION)

        logging.debug(WEBLOGIC_PATCHES + ": ")
        logging.debug(yaml.dump(weblogic_patches))
        __write_to_yaml(weblogic_patches, WEBLOGIC_PATCHES)

    end_timing(timing_key)

def get_weblogic_opatch_patches(session, yml, section, platform, release):
    timing_key = "weblogic opatch patches"
    start_timing(timing_key)
    
    patches = {}

    logging.info("Downloading " + str(len(yml[section])) + " patches for Weblogic OPatch Patches")
    downloaded = False
    for i, patch in enumerate(yml[section], start=1):
        file_name = __get_patch(session, patch, platform, release, WEBLOGIC_OPATCH_PATCHES)
        if file_name:
            downloaded = True
            patches["patch" + str(i)] = '%{hiera("peoplesoft_base")}/dpk/cpu_archives/' + WEBLOGIC_OPATCH_PATCHES + '/' + file_name

    if downloaded:
        logging.debug(WEBLOGIC_OPATCH_PATCHES + ": ")
        logging.debug(yaml.dump(patches))
        __write_to_yaml(patches, WEBLOGIC_OPATCH_PATCHES)

    end_timing(timing_key)

def get_tuxedo_patches(session, yml, section, platform, release):
    timing_key = "tuxedo patches"
    start_timing(timing_key)
    
    tuxedo_patches = {}
    tuxedo_patches_version = {}

    logging.info("Downloading " + str(len(yml[section])) + " patches for Tuxedo")
    downloaded = False
    for i, patch in enumerate(yml[section], start=1):
        patch,version=patch.split(':', 1)
        file_name = __get_patch(session, patch, platform, release, TUXEDO_PATCHES)
        if file_name:
            downloaded = True
            tuxedo_patches_version["patch" + str(i)] = str(version)
            tuxedo_patches["patch" + str(i)] = '%{hiera("peoplesoft_base")}/dpk/cpu_archives/' + TUXEDO_PATCHES + '/' + file_name

    if downloaded:
        logging.debug(TUXEDO_PATCHES_VERSION + ": ")
        logging.debug(yaml.dump(tuxedo_patches_version))
        __write_to_yaml(tuxedo_patches_version, TUXEDO_PATCHES_VERSION)

        logging.debug(TUXEDO_PATCHES + ": ")
        logging.debug(yaml.dump(tuxedo_patches))
        __write_to_yaml(tuxedo_patches, TUXEDO_PATCHES)

    end_timing(timing_key)

def get_oracleclient_patches(session, yml, section, platform, release):
    timing_key = "oracleclient patches"
    start_timing(timing_key)
    
    oracleclient_patches = {}
    oracleclient_patches_version = {}

    logging.info("Downloading " + str(len(yml[section])) + " patches for Oracle Client")
    downloaded = False
    for i, patch in enumerate(yml[section], start=1):
        file_name = __get_patch(session, patch, platform, release, ORACLECLIENT_PATCHES)
        if file_name:
            downloaded = True
            oracleclient_patches_version["patch" + str(i)] = str(patch)
            oracleclient_patches["patch" + str(i)] = '%{hiera("peoplesoft_base")}/dpk/cpu_archives/' + ORACLECLIENT_PATCHES + '/' + file_name

    if downloaded:
        logging.debug(ORACLECLIENT_PATCHES_VERSION + ": ")
        logging.debug(yaml.dump(oracleclient_patches_version))
        __write_to_yaml(oracleclient_patches_version, ORACLECLIENT_PATCHES_VERSION)

        logging.debug(ORACLECLIENT_PATCHES + ": ")
        logging.debug(yaml.dump(oracleclient_patches))
        __write_to_yaml(oracleclient_patches, ORACLECLIENT_PATCHES)

    end_timing(timing_key)

def get_oracleclient_opatch_patches(session, yml, section, platform, release):
    timing_key = "oracleclient opatch patches"
    start_timing(timing_key)
    
    patches = {}

    logging.info("Downloading " + str(len(yml[section])) + " patches for Oracle Client OPatch Patches")
    downloaded = False
    for i, patch in enumerate(yml[section], start=1):
        file_name = __get_patch(session, patch, platform, release, section)
        if file_name:
            downloaded = True
            patches["patch" + str(i)] = '%{hiera("peoplesoft_base")}/dpk/cpu_archives/' + ORACLECLIENT_OPATCH_PATCHES + '/' + file_name

    if downloaded:
        logging.debug(ORACLECLIENT_OPATCH_PATCHES + ": ")
        logging.debug(yaml.dump(patches))
        __write_to_yaml(patches, ORACLECLIENT_OPATCH_PATCHES)

    end_timing(timing_key)

def get_jdk_patches(session, yml, section, platform, release):
    timing_key = "jdk patches"
    start_timing(timing_key)
    
    jdk_patches = {}
    jdk_patches_version = {}

    logging.info("Downloading " + str(len(yml[section])) + " patches for JDK")
    downloaded = False
    for i, patch in enumerate(yml[section], start=1):
        patch,version = patch.split(':', 1)
        simple_verison = version.replace('.', '')
        file_name = __get_patch(session, patch, platform, version, JDK_PATCHES)
        if file_name:
            downloaded = True
            jdk_patches_version["patch" + str(i)] = str(simple_verison)
            jdk_patches["patch" + str(i)] = '%{hiera("peoplesoft_base")}/dpk/cpu_archives/' + JDK_PATCHES + '/' + file_name

    if downloaded:
        logging.debug(JDK_PATCHES_VERSION + ": ")
        logging.debug(yaml.dump(jdk_patches_version))
        __write_to_yaml(jdk_patches_version, JDK_PATCHES_VERSION)

        logging.debug(JDK_PATCHES + ": ")
        logging.debug(yaml.dump(jdk_patches))
        __write_to_yaml(jdk_patches, JDK_PATCHES)

    end_timing(timing_key)

# MOS Functions
def __get_mos_authentication():
    # Copied from ioco - thanks Kyle!
    timing_key = "__get_mos_authentication"
    start_timing(timing_key)
    
    logging.info("Authenticating with MOS")
    logging.debug("Creating auth cookie from MOS")
    cookie_file = os.path.join(this.config[TEMP], 'mos.cookie')

    # eat any old cookies
    if os.path.exists(cookie_file):
        os.remove(cookie_file)
        
    try:
        # Create a session and update headers
        s = requests.session()
        s.headers.update({'User-Agent': 'Mozilla/5.0'})

        # Initiate updates.oracle.com request to get login redirect URL
        logging.debug('Requesting downloads page')
        r = s.get("https://updates.oracle.com/Orion/Services/download", allow_redirects=False)
        login_url = r.headers['Location']
        if not login_url:
            logging.error("Location was empty so login URL can't be set") 
            error_timings(timing_key)
            exit(2)

        # Create a NEW session, then send Basic Auth to login redirect URL
        logging.debug('Sending Basic Auth to login, using new session')
        s = requests.session()
        logging.debug("Using MOS username: " + this.config.get('mos_username'))
        decoded = cryptocode.decrypt(this.config.get('mos_password'), "NIswEgoOj39wpzJcqocQ8mw4iMkqtS")
        r = s.post(login_url, auth = HTTPBasicAuth(this.config.get('mos_username'), decoded))
            
        # Save session cookies to be used by downloader later on...
        this.config['mos_cookies'] = s.cookies

        # Validate login was success
        if r.ok:
            logging.info(" - MOS Login was Successful")
        else:
            logging.error(" - MOS login was NOT successful.")
            error_timings(timing_key)
            exit(2)
    except:
        logging.error(" - Issue getting MOS auth token")
        end_timing(timing_key)
        exit(4)

    end_timing(timing_key)
    return s

def __get_patch(session, patch, platform, release, product):
    # Copied from ioco - thanks Kyle!
    if not __get_patch_status(patch):
        file_name = __find_mos_patch(session, patch, platform, release)
        logging.debug(" - Downloaded File Name: " + str(file_name))
    else:
        logging.info(" - Patch already downloaded: " + str(patch))
        return False

    if file_name:
        if product == JDK_PATCHES:
            logging.info(" - Converting JDK to DPK format")
            file_name = __convert_jdk_archive(file_name, release)
            logging.debug("JDK Files: " + file_name + " and Release: " + release)
        file = __copy_files(file_name, product, patch)

    return file

def __find_mos_patch(session, patch, platform, release):
    # timing_key = "__find_mos_patch"
    # start_timing(timing_key)

    logging.debug(" - Downloading files from MOS")
    try:
        # Use same session to search for downloads
        logging.debug('Search for list of downloads, using same session')
        mos_uri_search = "https://updates.oracle.com/Orion/SimpleSearch/process_form?search_type=patch&patch_number=" + str(patch) + "&plat_lang=" + str(platform)
        r = session.get(mos_uri_search) 
        search_results = r.content.decode('utf-8')
        
        # Validate search results
        if r.ok:
            logging.debug("Search results return success")
        else:
            logging.error("Search results did NOT return success")
            # error_timings(timing_key)
            exit(3)
    except:
        logging.error("Issue getting MOS search results")
        # end_timing(timing_key)
        raise

    try:
        # Extract download links to list
        if release:
            simple_release = release.replace('.', '')
            pattern = "https.+?Download\/process_form\/.*" + simple_release + ".*\.zip*"
        else:
            pattern = "https.+?Download\/process_form\/.*\.zip*"
        logging.debug("Search Pattern: " + pattern)
        download_links = re.findall(pattern,search_results)
        download_links_file = os.path.join(this.config[TEMP], 'mos-download.links')
        # Write download links to file
        f = open(download_links_file,"w")
        for link in download_links:
            # Write download links list to file
            logging.debug(link)
            f.write(link + os.linesep)
        f.close()

        # Validate download links
        if len(download_links) > 0:
            logging.debug(" - Downloading " + str(len(download_links)) + " files")
            logging.debug(" - URL: " + str(download_links))
        else:
            logging.error("No download links found")
            # error_timings(timing_key)
            exit(2)
    except:
        logging.error("Issue creating download links file")
        # end_timing(timing_key)
        raise

    # multi thread download
    # results = ThreadPool(this.config.get('download_threads')).imap_unordered(__download_file, download_links)
    results = __download_file(download_links)
    logging.debug("Download Results: " + str(results))

    # end_timing(timing_key)
    return results

def __copy_files(file, product, patch):

    # for file in files:
    tmp_file = os.path.join(this.config[TEMP], file)
    target_dir = os.path.join(this.config[ARCHIVE], product, file)

    logging.debug("    Moving to patch from  " + str(tmp_file) + " to " + str(target_dir))
    try:
        shutil.move(tmp_file, target_dir)
        logging.debug("    - [DONE] " + file)
    except FileNotFoundError: 
        logging.error(" - Patch file " + file + " not found")
    except PermissionError: 
        logging.error(" - You do not have permssion to copy to " + target_dir)
    except NotADirectoryError:
        logging.error(" - The target directory is incorrect: " + target_dir)
    except:
        logging.error(" - Encountered an error moving the patch to the cpu_archives/ " + str(product) + " folder")

    __update_patch_status(patch, True)
    logging.debug("Update Patch Status - " + str(patch) + ": true")

    return file # The last filename - should only be one patch in the list

def __download_file(urls):
    # assumes that the last segment after the / represents the file name
    # if url is abc/xyz/file.txt, the file name will be file.txt
    for url in urls:
        file_name_start_pos = url.rfind("=") + 1
        file_name = url[file_name_start_pos:]
        s = requests.session()
        s.cookies =  this.config.get('mos_cookies') 
        r = s.get(url, stream=True, allow_redirects=True)
        logging.debug("Response Code: " + str(r.status_code))
        if r.status_code == 302:
            r = s.get(r.headers['Location'])
            logging.debug("Redirect URL: " + str(r.headers['Location']))
        if r.status_code == requests.codes.ok:
            with open(this.config[TEMP] + "/" + file_name, 'wb') as f: 
                for data in r:
                    f.write(data)

    return file_name

# File Management Functions
def __validate_input():

    with open(os.path.join(os.getcwd(), 'codes', 'codes.yaml')) as c:
        this.codes = yaml.load(c, Loader=yaml.FullLoader)

    with open(this.config.get('src_yaml'), 'r') as f:
        yml = yaml.load(f, Loader=yaml.FullLoader)
        logging.debug(json.dumps(yml, indent=2))

    # Validate input file has required sections
    try:
        platform_name = yml.get('platform')
        this.config['platform'] = platform_name
        if platform_name:
            platform = this.codes['platform'][yml['platform']]
            logging.debug("Platform - " + yml['platform'] + ": " + platform)
        else:
            logging.error("Input YAML file must specify 'platform: <value>'")
        ptversion = yml.get(PEOPLETOOLS)
        this.config['ptversion'] = ptversion
        if ptversion:
            logging.debug("Download patches for PeopleTools " + ptversion)
        else:
            logging.error("Input YAML file must specify 'peopletools: <value>'")
    except:
        exit(2)

    return yml, ptversion, platform

def __create_patch_status():
    if not os.path.exists(this.config.get(STATUS)):
        logging.debug("Patch Status File missing - creating it now")
        try:
            with open(this.config.get(STATUS),'w') as f:
                patch_status = {}
                json.dump(patch_status, f)
        except FileNotFoundError:
            logging.error("Patch status file not created. Try again with `byop config`")
            exit(2)
        except:
            logging.error("Issue creating Patch status file")
            raise

def __get_patch_status(patch):
    # Checking Patch download status
    if not this.config.get('redownload'):
        if not os.path.exists(this.config.get(STATUS)):
            __create_patch_status()
        try:
            with open(this.config.get(STATUS)) as f:
                patch_status = json.load(f)
        except:
            logging.error("Issue opening Patch status file")

        logging.debug("Patch status: \n" + json.dumps(patch_status))
        try:
            if patch_status[str(patch)]:
                return True
        except:
            return False
    else:
        logging.debug("Redownload Flag is set - skipping check of patch status")
        pass

def __update_patch_status(step, status):
    try:
        with open(this.config.get(STATUS), 'r+') as f:
            patch_status = json.load(f)
            patch_status[step] = status
            f.seek(0)
            f.truncate()
            json.dump(patch_status, f, indent=2)
    except:
        logging.error('Issue updating patch status json file')

def __write_to_yaml(dict, header):

    if os.path.exists(this.config.get('tgt_yaml')):
        with open(this.config.get('tgt_yaml'), 'r') as tgt_yaml:
            tgt = yaml.load(tgt_yaml, Loader=yaml.FullLoader) or {}
    else:
        tgt = {}

    tgt.pop(header, None)
    tgt[header] = dict
    
    with open(this.config.get('tgt_yaml'), 'w') as tgt_yaml:
        yaml.dump(tgt, tgt_yaml, sort_keys=True, indent=2)

def __convert_jdk_archive(file, release):

    zip_file = os.path.join(this.config.get(TEMP), file)
    logging.debug("Zip file: " + str(zip_file))
    
    if this.config.get('platform') == 'linux':
        tarfile_orig =  os.path.join(this.config.get(TEMP), 'jdk-' + release + '_linux-x64_bin.tar.gz')
        logging.debug("Delivered Tarball: " + str(tarfile_orig))
    elif this.config.get('platform') == 'windows':
        tarfile_orig =  os.path.join(this.config.get(TEMP), 'jdk-' + release + '_windows-x64_bin.zip')
        logging.debug("Delivered Tarball: " + str(tarfile_orig))


    tarfile_pt = os.path.join(this.config.get(TEMP), 'pt-jdk-' + release + '.tgz')
    tarfile_dir = os.path.join(this.config.get(TEMP), 'tar')
    try:
        os.makedirs(tarfile_dir, exist_ok = True)
    except OSError as error:
        logging.error("Directory '%s' can not be created" % tarfile_dir)
    
    # Extract the .zip
    logging.debug("  - JDK - unzipping download")
    with zipfile.ZipFile(zip_file) as zipf:
        zipf.extractall(this.config[TEMP])

    if this.config.get('platform') == 'linux':
        # Extract the .tar.gz file - it contains an extra top directory that breaks with the DPK
        if (os.path.exists(tarfile_orig)):
            logging.debug("Cleanup tmp/tar directory before re-extracting JDK tarball")
            # JDK tar permissions cause errors when cleanup is run - change them before?
            files = glob.glob(config.get(TEMP) + "/tar/*", recursive=True)
            if files:
                for f in files:
                    try:
                        shutil.rmtree(f)
                        logging.debug("Removed file: " + str(f))
                    except OSError as e:
                        logging.error("Error: %s : %s" % (f, e.strerror))
            logging.debug("  - JDK - untarring .tar.gz file to remove parent directory")
            tar1 = tarfile.open(tarfile_orig)
            tar1.extractall(path=tarfile_dir) #, set_attrs=False)
            tar1.close
        else:
            logging.error("No tarball matching filename found: " + tarfile_orig)
    elif this.config.get('platform') == 'windows':
        # Extract the .zip
        logging.debug("  - JDK - unzipping download")
        with zipfile.ZipFile(tarfile_orig) as zipf:
            zipf.extractall(tarfile_dir)

    # Repackage the tarball and rename for the DPK
    logging.debug("  - JDK - creating DPK compatible .tgz")
    logging.debug("  - Source: " + str(tarfile_dir))
    file = __tardirectory(tarfile_dir, tarfile_pt)
    logging.debug("DPK Compatible JDK Archive: " + os.path.basename(file))

    shutil.rmtree(tarfile_dir)
    return os.path.basename(file)

def __tardirectory(path, name):
    original_dir = os.getcwd()
    top_level_folder = next(os.walk(path))[1][0]
    os.chdir(os.path.join(path, top_level_folder))
    logging.debug("Top Level Folder Name: " + top_level_folder)

    with tarfile.open(name, "w:gz") as tarhandle:
        for root, dirs, files in os.walk(os.getcwd()):
            for file in files:
                tarhandle.add(os.path.relpath(os.path.join(root, file)))

    os.chdir(original_dir)
    return name

def __zipdirectory(filename, folders):
    with zipfile.ZipFile(os.path.join(this.config.get(OUTPUT), filename),'a') as zip:
    
        original_dir = os.getcwd()
        os.chdir(this.config.get(OUTPUT))
        for folder in folders:
            path = os.path.join(os.path.basename(this.config.get(ARCHIVE)), folder)

            logging.debug("Zip path: " + path)
            logging.debug("Zip file: " + str(zip))
            for dirname, subdirs, files in os.walk(path):
                zip.write(dirname)
                for filename in files:
                    zip.write(os.path.join(dirname, filename))

    os.chdir(original_dir)

def __zipyaml(filename, file):
    with zipfile.ZipFile(os.path.join(this.config.get(OUTPUT), filename),'a') as zip:
        original_dir = os.getcwd()
        os.chdir(this.config.get(OUTPUT))
        logging.info("Adding psft_patches.yaml to zip")
        zip.write(os.path.join(file))

    os.chdir(original_dir)


# Logging and Timings
def setup_logging():

    if this.config.get("verbose") == True:
        loglevel=logging.DEBUG
    else:
        loglevel=logging.INFO
    
    rootLogger = logging.getLogger()
    rootLogger.setLevel(loglevel)

    fileHandler = logging.FileHandler('{0}'.format('byop.log'), mode='a')
    fileFormatter = logging.Formatter('%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s')
    fileHandler.setFormatter(fileFormatter)
    fileHandler.setLevel(loglevel)
    rootLogger.addHandler(fileHandler)

    consoleHandler = logging.StreamHandler()
    consoleFormatter = logging.Formatter('[%(levelname)-5.5s]  %(message)s')
    consoleHandler.setFormatter(consoleFormatter)
    consoleHandler.setLevel(loglevel)
    rootLogger.addHandler(consoleHandler)

    logging.debug('Debug Log File: byop.log')

def init_timings():
    this.timings = {}
    this.timings[this.total_time_key] = datetime.datetime.now()

def start_timing(name):
    this.timings[name] = datetime.datetime.now()

def end_timing(name):
    # if timing duration has been calculated, skip
    if not isinstance(this.timings[name], datetime.timedelta):
        start_time = this.timings[name]
        this.timings[name] = datetime.datetime.now() - start_time

def error_timings(name):
    end_timing(name)
    print_timings()

def print_timings():

    if not this.timings_printed and not this.config['quiet']:

        # if total time has been calculated by a previous call, skip
        if not isinstance(this.timings[this.total_time_key], datetime.timedelta): 
            this.timings[this.total_time_key] = datetime.datetime.now() - this.timings[this.total_time_key]

        logging.debug("Raw Timings:")
        logging.debug("------------")
        for key, value in this.timings.items():
            logging.debug(key + ": " + str(value) )

        header = "---------------------------------------"
        print(header)
        for name in this.timings:
            if not this.total_time_key in name:
                if not isinstance(this.timings[name], datetime.timedelta):
                    end_timing(name)
                duration = this.timings[name]
                hours, remainder = divmod(duration.total_seconds(), 3600)
                minutes, seconds = divmod(remainder, 60)
                print( '{:29}'.format(name) + ": {:02.0f}:{:02.0f}:{:02.0f}".format(hours, minutes, seconds) )

        print(header)

        duration = this.timings[this.total_time_key]
        hours, remainder = divmod(duration.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        print( '{:29}'.format(this.total_time_key) + ": {:02.0f}:{:02.0f}:{:02.0f}".format(hours, minutes, seconds) )

        print(header)

        this.timings_printed = True
