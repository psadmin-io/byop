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
from pathlib import Path
from http.cookiejar import MozillaCookieJar
from multiprocessing.pool import ThreadPool
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
JDK_PATCHES = "jdk_patches"
JDK_PATCHES_VERSION = "jdk_patches_version"
ORACLECLIENT_OPATCH_PATCHES = "oracleclient_opatch_patches"
ORACLECLIENT_PATCHES = "oracleclient_patches"
ORACLECLIENT_PATCHES_VERSION = "oracleclient_patches_version"
TUXEDO_PATCHES = "tuxedo_patches"
TUXEDO_PATCHES_VERSION = "tuxedo_patches_version"
WEBLOGIC_OPATCH_PATCHES = "weblogic_opatch_patches"
WEBLOGIC_PATCHES = "weblogic_patches"
WEBLOGIC_PATCHES_VERSION = "weblogic_patches_version"

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

    if not config.get('archive_dir'):
        this.config['archive_dir'] = os.path.join(os.getcwd(), 'cpu_archives')
    if not config.get('tmp_dir'):
        this.config['tmp_dir'] = os.path.join(os.getcwd(), 'tmp')
    if not config.get('patch_status_file'):
        this.config['patch_status_file'] = os.path.join(this.config['tmp_dir'], 'patch_status_file')

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

    config["mos_username"] = mos_username
    config["mos_password"] = mos_password
    config.save()
    logging.info("Configuration save to config.json")

# ####### #
# cleanup #
# ####### #
@cli.command()
@click.option('--yaml',
              is_flag=True,
              default=False,
              help="Include psft_patches.yaml in cleanup")
@click.option('--tgt-yaml', 
              help="Target YAML file to delete. Default is psft_patches.yaml.",
              default='psft_patches.yaml')
@pass_config
@common_options
def cleanup(config, yaml, tgt_yaml, verbose, quiet):
    """Remove files from the tmp and cpu_archives directories."""
    this.config['verbose'] = verbose
    this.config['quiet'] = quiet
    setup_logging()

    files = glob.glob(config.get('archive_dir') + "/*/*", recursive=True)
    if files:
        for f in files:
            try:
                os.remove(f)
                logging.info("Removed file: " + str(f))
            except OSError as e:
                logging.error("Error: %s : %s" % (f, e.strerror))
    else:
        logging.info("No patches to cleanup")

    files = glob.glob(config.get('tmp_dir') + "/*", recursive=True)
    if files:
        for f in files:
            try:
                os.remove(f)
                logging.info("Removed file: " + str(f))
            except OSError as e:
                logging.error("Error: %s : %s" % (f, e.strerror))
    else:
        logging.info("No temporary files to cleanup")

    if yaml:
        if os.path.exists(tgt_yaml):
            try:
                os.remove(tgt_yaml)
                logging.info("Removed file: " + str(tgt_yaml))
            except OSError as e:
                logging.error("Error: %s : %s" % (tgt_yaml, e.strerror))
        else:
            logging.info("No " + tgt_yaml + " file to cleanup")

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
    this.config['tgt_yaml'] = tgt_yaml
    logging.debug("Source YAML: " + this.config['tgt_yaml'])
    logging.debug("Target YAML: " + this.config['tgt_yaml'])
    logging.debug(this.config['mos_username'])

    init_timings()
    build_directories()
    download_patches()
    print_timings()
    pass

# ################# #
# Library Functions #
# ################# #
def build_directories():
    try:
        os.makedirs(this.config['archive_dir'], exist_ok = True)
    except OSError as error:
        logging.error("Directory '%s' can not be created" % this.config['archive_dir'])

    try:
        os.makedirs(os.path.join(this.config['archive_dir'], WEBLOGIC_PATCHES), exist_ok = True)
    except OSError as error:
        logging.error("Directory '%s' can not be created" % os.path.join(this.config['archive_dir'], WEBLOGIC_PATCHES))
    try:
        os.makedirs(os.path.join(this.config['archive_dir'], WEBLOGIC_OPATCH_PATCHES), exist_ok = True)
    except OSError as error:
        logging.error("Directory '%s' can not be created" % os.path.join(this.config['archive_dir'], WEBLOGIC_OPATCH_PATCHES))
    try:
        os.makedirs(os.path.join(this.config['archive_dir'], TUXEDO_PATCHES), exist_ok = True)
    except OSError as error:
        logging.error("Directory '%s' can not be created" % os.path.join(this.config['archive_dir'], TUXEDO_PATCHES))
    try:
        os.makedirs(os.path.join(this.config['archive_dir'], JDK_PATCHES), exist_ok = True)
    except OSError as error:
        logging.error("Directory '%s' can not be created" % os.path.join(this.config['archive_dir'], JDK_PATCHES))

    try:
        os.makedirs(os.path.join(this.config['tmp_dir']), exist_ok = True)
    except OSError as error:
        logging.error("Directory '%s' can not be created" % os.path.join(this.config['tmp_dir']))

def download_patches():
    with open(os.path.join(os.getcwd(), 'codes', 'codes.yaml')) as c:
        this.codes = yaml.load(c, Loader=yaml.FullLoader)

    with open(this.config.get('src_yaml'), 'r') as f:
        yml = yaml.load(f, Loader=yaml.FullLoader)
        logging.debug(json.dumps(yml, indent=2))

    try:
        platform = this.codes['platform'][yml['platform']]
        logging.debug("Platform - " + yml['platform'] + ": " + platform)
    except NameError:
        logging.error("Input YAML file must specify platform")
        raise

    try:
        ptversion = yml['peopletools']
        logging.debug("Download patches for PeopleTools " + ptversion)
    except NameError:
        logging.error("Input YAML file must specify PeopleTools")
        raise

    try:
        if yml[WEBLOGIC_PATCHES_VERSION]:
            logging.info(this.codes['peopletools'])
            release = this.codes['peopletools'][str(ptversion)]['weblogic']
            logging.debug("PeopleTools - " + yml['peopletools'] + ": " + release)
            get_weblogic_patches(yml, WEBLOGIC_PATCHES_VERSION, platform, release)
    except NameError:
        logging.info("No Weblogic Patches: " + NameError)

    try:
        if yml[WEBLOGIC_OPATCH_PATCHES]:
            
            release = this.codes['peopletools'][yml['peopletools']]['weblogic_opatch']
            logging.debug("PeopleTools - " + yml['peopletools'] + ": " + release)
            get_weblogic_opatch_patches(yml, WEBLOGIC_OPATCH_PATCHES, platform, release)
    except NameError:
        logging.info("No Weblogic OPatch Patches")

def get_weblogic_patches(yml, section, platform, release):
    timing_key = "weblogic patches"
    start_timing(timing_key)
    
    weblogic_patches = {}
    weblogic_patches_version = {}

    logging.info("Downloading " + str(len(yml[section])) + " patches for Weblogic")
    downloaded = False
    for i, patch in enumerate(yml[section], start=1):
        logging.info(" - Downloading WebLogic Patch: " + str(patch))
        file_name = get_patch(patch, platform, release, section)
        if file_name:
            downloaded = True
            weblogic_patches_version["patch" + str(i)] = str(patch)
            weblogic_patches["patch" + str(i)] = '%{hiera("peoplesoft_base")}/dpk/cpu_archives/' + section + '/' + file_name

    if downloaded:
        logging.debug("weblogic_patches_version: ")
        logging.debug(yaml.dump(weblogic_patches_version))
        __write_to_yaml(weblogic_patches_version, section)

        logging.debug("weblogic_patches: ")
        logging.debug(yaml.dump(weblogic_patches))
        __write_to_yaml(weblogic_patches, WEBLOGIC_PATCHES)

    
    end_timing(timing_key)

def get_weblogic_opatch_patches(yml, section, platform, release):
    timing_key = "weblogic opatch patches"
    start_timing(timing_key)
    
    patches = {}

    logging.info("Downloading " + str(len(yml[section])) + " patches for " + timing_key)
    downloaded = False
    for i, patch in enumerate(yml[section], start=1):
        logging.info(" - Downloading Patch: " + str(patch))
        file_name = get_patch(patch, platform, release, section)
        if file_name:
            downloaded = True
            # weblogic_patches_version["patch" + str(i)] = str(patch)
            patches["patch" + str(i)] = '%{hiera("peoplesoft_base")}/dpk/cpu_archives/' + section + '/' + file_name

    if downloaded:
        logging.debug(section + ": ")
        logging.debug(yaml.dump(patches))
        __write_to_yaml(patches, section)

    end_timing(timing_key)

def get_patch(patch, platform, release, product):
    timing_key = "__get_patch"
    if not __get_patch_status(patch, timing_key):
        logging.debug("Patch not downloaded")
        file_name = __get_mos_patch(patch, platform, release, product)
        return file_name
    else:
        logging.info("Patch already downloaded: " + str(patch))
        return False

def __get_mos_patch(patch, platform, release, product):
    # Copied from ioco - thanks Kyle!
    logging.info(" - Downloading files from MOS")
    timing_key = "__get_mos_patch"
    start_timing(timing_key)
    
    logging.debug("Creating auth cookie from MOS")
    cookie_file = os.path.join(this.config['tmp_dir'], 'mos.cookie')

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
        r = s.post(login_url, auth = HTTPBasicAuth(this.config.get('mos_username'), this.config.get('mos_password')))
            
        # Save session cookies to be used by downloader later on...
        this.config['mos_cookies'] = s.cookies

        # Validate login was success                 
        if r.ok:
            logging.debug("MOS login was successful")
        else:
            logging.error("MOS login was NOT successful.")
            error_timings(timing_key)
            exit(2)
    except:
        logging.error("Issue getting MOS auth token")
        end_timing(timing_key)
        raise

    try:
        # Use same session to search for downloads
        logging.debug('Search for list of downloads, using same session')
        mos_uri_search = "https://updates.oracle.com/Orion/SimpleSearch/process_form?search_type=patch&patch_number=" + str(patch) + "&plat_lang=" + str(platform)
        r = s.get(mos_uri_search) 
        search_results = r.content.decode('utf-8')
        
        # Validate search results                 
        if r.ok:
            logging.debug("Search results return success")
        else:
            logging.error("Search results did NOT return success")
            error_timings(timing_key)
            exit(2)
    except:
        logging.error("Issue getting MOS search results")
        end_timing(timing_key)
        raise
        
    try:        
        # Extract download links to list
        if release:
            pattern = "https.+?Download\/process_form\/.*" + release + ".*\.zip*"
        else:
            pattern = "https.+?Download\/process_form\/.*\.zip.*"
        logging.debug("Search Pattern: " + pattern)
        download_links = re.findall(pattern,search_results)
        download_links_file = os.path.join(this.config['tmp_dir'], 'mos-download.links')
        # Write download links to file
        f = open(download_links_file,"w")
        for link in download_links:
            # Write download links list to file
            logging.debug(link)
            f.write(link + os.linesep)
        f.close()

        # Validate download links
        if len(download_links) > 0:
            logging.info(" - Downloading " + str(len(download_links)) + " files")
        else:
            logging.error("No download links found")
            error_timings(timing_key)
            exit(2)
    except:
        logging.error("Issue creating download links file")
        end_timing(timing_key)
        raise

    # multi thread download
    results = ThreadPool(this.config.get('download_threads')).imap_unordered(__download_file, download_links)
    for r in results:
        target_dir = os.path.join(this.config['archive_dir'], product, r)
        logging.info("    Moving to patch to " + str(target_dir))
        try:
            shutil.move(os.path.join(this.config['tmp_dir'], r), target_dir)
        except:
            logging.error("Encountered an error moving the patch to the cpu_archives folder")
        logging.info("    [DONE] " + r)
        __update_patch_status(patch, True)
        logging.debug("Update Patch Status - " + str(patch) + ": true")
    

    end_timing(timing_key)
    return r # The last filename

def __download_file(url):
    # assumes that the last segment after the / represents the file name
    # if url is abc/xyz/file.txt, the file name will be file.txt
    file_name_start_pos = url.rfind("=") + 1
    file_name = url[file_name_start_pos:]
    s = requests.session()
    s.cookies =  this.config.get('mos_cookies') 
    r = s.get(url, stream=True)
    if r.status_code == requests.codes.ok:
        with open(this.config['tmp_dir'] + "/" + file_name, 'wb') as f: 
            for data in r:
                f.write(data)

    return file_name

def __get_patch_status(patch, timing_key):
    # Checking Patch download status
    if not this.config.get('redownload'):
        if not os.path.exists(this.config.get('patch_status_file')):
            logging.debug("Patch Status File missing - creating it now")
            try:
                with open(this.config.get('patch_status_file'),'w') as f:
                    patch_status = {}
                    json.dump(patch_status, f)
            except FileNotFoundError:
                logging.error("Patch files directory not created. Try again with `byop directories`")
                error_timings(timing_key)
                exit(2)
            except:
                logging.error("Issue creating Patch status file")
                raise
        else:
            try:
                with open(this.config.get('patch_status_file')) as f:
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
        logging.info("Redownload Flag is set - skipping check of patch status")
        pass

def __update_patch_status(step, status):
    try:
        with open(this.config.get('patch_status_file'), 'r+') as f:
            patch_status = json.load(f)
            patch_status[step] = status
            f.seek(0)
            f.truncate()
            json.dump(patch_status, f)
    except:
        logging.error('Issue updating patch status json file')

def __write_to_yaml(dict, header):

    with open(this.config.get('tgt_yaml'), 'r') as tgt_yaml:
        tgt = yaml.load(tgt_yaml, Loader=yaml.FullLoader) or {}

    tgt.pop(header, None)
    tgt[header] = dict
    
    with open(this.config.get('tgt_yaml'), 'w') as tgt_yaml:
        yaml.dump(tgt, tgt_yaml, sort_keys=True, indent=2)

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
