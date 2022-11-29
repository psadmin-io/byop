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
    # this = sys.modules[__name__]
    # this.timings = None
    # this.total_time_key = 'TOTAL TIME'
    # this.timings_printed = False
    pass  

@pass_config
def init(config):
    if not config.get('archive_dir'):
        this.config['archive_dir'] = os.getcwd() + '/cpu_archives'
    if not config.get('tmp_dir'):
        this.config['tmp_dir'] = os.getcwd() + '/tmp'

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
@pass_config
def build(config, src_yaml, tgt_yaml, verbose):

    if not config.get('verbose'):
        this.config['verbose'] = verbose
    if not config.get('download_threads'):
        this.config['download_threads'] = 2

    init()

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
            for patch in yml[WEBLOGIC_VERSION]:
                get_weblogic_patches(patch, platform)
        if yml[WEBLOGIC_VERSION]:

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

    logging.info("Directories created")

def get_weblogic_patches(patch, platform):
    # timing_key = "dpk deploy"
    # start_timing(timing_key)

    logging.info("Downloading patch: " + str(patch))
    __get_dpk_mos(patch, platform, WEBLOGIC)


# Copied from ioco - thanks Kyle!
def __get_dpk_mos(patch_id, platform_id, product):
    logging.info(" - Downloading files from MOS")
    timing_key = "dpk deploy __get_dpk_mos"
    # util.start_timing(timing_key)
    
    logging.debug("Creating auth cookie from MOS")
    cookie_file = 'mos.cookie'

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
            # util.error_timings(timing_key)
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
            # util.error_timings(timing_key)
            exit(2)
    except:
        logging.error("Issue getting MOS auth token")
        # util.end_timing(timing_key)
        raise

    try:
        # Use same session to search for downloads
        logging.debug('Search for list of downloads, using same session')
        mos_uri_search = "https://updates.oracle.com/Orion/SimpleSearch/process_form?search_type=patch&patch_number=" + str(patch_id) + "&" + str(platform_id)
        r = s.get(mos_uri_search) 
        search_results = r.content.decode('utf-8')
        
        # Validate search results                 
        if r.ok:
            logging.debug("Search results return success")
        else:
            logging.error("Search results did NOT return success")
            # util.error_timings(timing_key)
            exit(2)
    except:
        logging.error("Issue getting MOS search results")
        # util.end_timing(timing_key)
        raise
        
    try:        
        # Extract download links to list
        pattern = "https://.+?Download/process_form/[^\"]*.zip[^\"]*"
        download_links = re.findall(pattern,search_results)
        download_links_file = 'mos-download.links'
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
            # util.error_timings(timing_key)
            exit(2)
    except:
        logging.error("Issue creating download links file")
        # util.end_timing(timing_key)
        raise

    # multi thread download
    results = ThreadPool(this.config.get('download_threads')).imap_unordered(__download_file, download_links)
    for r in results:
        target_dir = os.path.join(this.config['archive_dir'], product, r)
        logging.info("    Moving to patch to " + str(target_dir))
        shutil.move(os.path.join(this.config['tmp_dir'], r), target_dir)
        logging.info("    [DONE] " + r)

    
    logging.debug("Update DPK status - downloaded_patch_files: true")
    # util.end_timing(timing_key)

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

    if not this.timings_printed and not this.config['--quiet']:

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

# if __name__ == '__main__':
#     cli()

