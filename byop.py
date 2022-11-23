"""byop - Bring Your Own Patches - Infrastructure DPK Builder

Usage:
  byop

Options:
  --src-yaml=<file>    List of patches to build (Default: byop.yaml).
  --tgt-yaml=<file>    Output file (Default: psft_patches.yaml).
  --logs=<dir>         Log folder
  --verbose            Enable debug logging
  -h --help            Show this screen.

"""
import os
import sys
import logging
import datetime
from docopt import docopt
from pathlib import Path

this = sys.modules[__name__]
this.config = None
this.timings = None
this.total_time_key = 'TOTAL TIME'
this.timings_printed = False

def setup_logging(config):
    if config['--verbose']:
        loglevel=logging.DEBUG
    else:
        loglevel=logging.INFO
    
    rootLogger = logging.getLogger()
    rootLogger.setLevel(loglevel)

    fileHandler = logging.FileHandler('{0}/{1}'.format(config['--logs'], config['mainlog']))
    fileFormatter = logging.Formatter('%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s')
    fileHandler.setFormatter(fileFormatter)
    fileHandler.setLevel(loglevel)
    rootLogger.addHandler(fileHandler)

    consoleHandler = logging.StreamHandler()
    consoleFormatter = logging.Formatter('[%(levelname)-5.5s]  %(message)s')
    consoleHandler.setFormatter(consoleFormatter)
    consoleHandler.setLevel(loglevel)
    rootLogger.addHandler(consoleHandler)

    logging.debug('log: ' + config['--logs'] + '/' + config['mainlog'])

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

def get_config(args):

  config = args
  config['--logs'] = os.getenv('BYOP_LOGS',args['--logs'])
  config['--verbose'] = os.getenv('BYOP_VERBOSE',args['--verbose'])
  config['--src-yaml'] = os.getenv('BYOP_SRC_YAML',args['--src-yaml'])
  config['--tgt-yaml'] = os.getenv('BYOP_TGT_YAML',args['--tgt-yaml'])

  if not config['--logs']:
      config['--logs'] = os.getcwd() + '/logs'
  if not config['--verbose']:
      config['--verbose'] = False
  if not config['--src-yaml']:
      config['--src-yaml'] = 'byop.yaml'
  if not config['--tgt-yaml']:
      config['--tgt-yaml'] = 'psft_patches.yaml'

  return config

def main():

  # Setup
  config = get_config(docopt(__doc__, version='byop 1.0'))
  setup_logging(config)
  logging.debug("Configuration: " + config)


  # Finalize
  print_timings

if __name__ == '__main__':
  arguments = docopt(__doc__, version='byop 1.0')
  print(arguments)
  # main()

