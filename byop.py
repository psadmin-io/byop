import os
import py
import re
import sys
import json
import yaml
import logging
import datetime
import click
import shutil
import requests
from pathlib import Path
from http.cookiejar import MozillaCookieJar
from multiprocessing.pool import ThreadPool
from requests.auth import HTTPBasicAuth

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
            f.write(json.dumps(self))

pass_config = click.make_pass_decorator(Config, ensure=True)
this = sys.modules[__name__]
this.config = None
this.timings = None
patch_yml = {}

WEBLOGIC = "weblogic_patches"
WEBLOGIC_VERSION = "weblogic_patches_version"

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
    pass  

@pass_config
def init(config):
    if not config.get('archive_dir'):
        this.config['archive_dir'] = os.path.join(os.getcwd(), 'cpu_archives')
    if not config.get('tmp_dir'):
        this.config['tmp_dir'] = os.path.join(os.getcwd(), 'tmp')
    if not config.get('patch_status_file'):
        this.config['patch_status_file'] = os.path.join(this.config['tmp_dir'], 'patch_status_file')

    setup_logging()

# ########### #
# directories #
# ########### #
@cli.command()
@pass_config
def directories(config):
    init()
    build_directories()
    pass

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
@click.option('--verbose', 
              default=False, 
              is_flag=True, 
              help="Enable debug logging")
@click.option('--quiet', 
              default=False, 
              is_flag=True, 
              help="Don't print timing output")
@pass_config
def build(config, src_yaml, tgt_yaml, verbose, quiet):

    if not config.get('verbose'):
        this.config['verbose'] = verbose
    if not config.get('quiet'):
        this.config['quiet'] = quiet
    if not config.get('download_threads'):
        this.config['download_threads'] = 2

    init()
    init_timings()

    logging.debug("Source YAML: " + src_yaml)
    logging.debug("Target YAML: " + tgt_yaml)
    logging.debug(this.config['mos_username'])

    with open(src_yaml, 'r') as f:
        yml = yaml.load(f, Loader=yaml.FullLoader)
        logging.debug(yml)

        build_directories()
        if yml['platform']:
            platform = yml['platform']
        if yml[WEBLOGIC_VERSION]:
            get_weblogic_patches(yml, platform)

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
        os.makedirs(os.path.join(this.config['archive_dir'], WEBLOGIC), exist_ok = True)
    except OSError as error:
        logging.error("Directory '%s' can not be created" % os.path.join(this.config['archive_dir'], WEBLOGIC))
    
    try:
        os.makedirs(os.path.join(this.config['tmp_dir']), exist_ok = True)
    except OSError as error:
        logging.error("Directory '%s' can not be created" % os.path.join(this.config['tmp_dir']))

def get_weblogic_patches(yml, platform):
    timing_key = "weblogic patches"
    start_timing(timing_key)
    
    weblogic_patches = {}
    weblogic_patches_version = {}
    i = 0
    for patch in yml[WEBLOGIC_VERSION]:
        logging.info("Downloading WebLogic Patch: " + str(patch))
        file_name = get_patch(patch, platform, WEBLOGIC)
        weblogic_patches_version["patch" + str(i)] = "patch"

    logging.debug("weblogic_patches_version: ")
    logging.debug(yaml.dump(weblogic_patches_version))

    # Add Weblogic Patches to psft_patches.yaml
    # patch_yml = 
    
    end_timing(timing_key)

def get_patch(patch, platform, product):
    timing_key = "__get_patch"
    if not __get_patch_status(patch, timing_key):
        logging.debug("Patch not downloaded")
        __get_mos_patch(patch, platform, product)
    else:
        logging.info("Patch already downloaded: " + str(patch))

# Copied from ioco - thanks Kyle!
def __get_mos_patch(patch, platform, product):
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
        mos_uri_search = "https://updates.oracle.com/Orion/SimpleSearch/process_form?search_type=patch&patch_number=" + str(patch) + "&" + str(platform)
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
        pattern = "https://.+?Download/process_form/[^\"]*.zip[^\"]*"
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
        shutil.move(os.path.join(this.config['tmp_dir'], r), target_dir)
        logging.info("    [DONE] " + r)
        update_patch_status(patch, True)
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

def update_patch_status(step, status):
    try:
        with open(this.config.get('patch_status_file'), 'r+') as f:
            patch_status = json.load(f)
            patch_status[step] = status
            f.seek(0)
            f.truncate()
            json.dump(patch_status, f)
    except:
        logging.error('Issue updating patch status json file')

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

    logging.debug('log: byop.log')

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
