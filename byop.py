import os
import py
import sys
import json
import yaml
import logging
import datetime
import click
from pathlib import Path


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

@click.group(no_args_is_help=True)
@click.option('--verbose', 
              default=False, 
              is_flag=True, 
              help="Enable debug logging")
@click.option('--logs',
              type=click.Path(),
              default=os.getcwd(),
              help="Change directory for logs")
@pass_config
def cli(config, verbose, logs):
    """Bring Your Own Patches - Infrastructure DPK Builder"""

    config.load()

    # Update defaults
    if not config.get('verbose'):
        config['verbose'] = verbose
    if not config.get('logs'):
        config["logs"] = logs

    setup_logging(config)

    # Timings setup 
    this = sys.modules[__name__]
    this.timings = None
    this.total_time_key = 'TOTAL TIME'
    this.timings_printed = False
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
# @click.option('--verbose', 
#               default=False, 
#               is_flag=True, 
#               help="Enable debug logging")
# @click.option('--logs',
#               type=click.Path(),
#               default=os.getcwd() + '/logs',
#               help="Change directory for logs")
@pass_config
def build(config, src_yaml, tgt_yaml):
    click.echo("Source YAML: " + src_yaml)
    click.echo("Target YAML: " + tgt_yaml)

    click.echo(config['mos_username'])

    with open(src_yaml, 'r') as f:
        yml = yaml.load(f, Loader=yaml.FullLoader)
        click.echo(yml)
    pass


@cli.command()
@pass_config
def say_hello(config):
    """say hello to someone"""
    click.echo("Hello, %s" % config.get("mos_username", "MOS Username"))


# ################# #
# Library Functions #
# ################# #
def setup_logging(config):
    if config.get("verbose") == True:
        loglevel=logging.DEBUG
    else:
        loglevel=logging.INFO
    
    rootLogger = logging.getLogger()
    rootLogger.setLevel(loglevel)

    fileHandler = logging.FileHandler('{0}/{1}'.format(config.get("logs"), 'byop.log'), mode='a')
    fileFormatter = logging.Formatter('%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s')
    fileHandler.setFormatter(fileFormatter)
    fileHandler.setLevel(loglevel)
    rootLogger.addHandler(fileHandler)

    consoleHandler = logging.StreamHandler()
    consoleFormatter = logging.Formatter('[%(levelname)-5.5s]  %(message)s')
    consoleHandler.setFormatter(consoleFormatter)
    consoleHandler.setLevel(loglevel)
    rootLogger.addHandler(consoleHandler)

    logging.debug('log: ' + config.get("logs") + '/byop.log')

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

# def main():

#   # Setup
#   config = get_config(docopt(__doc__, version='byop 1.0'))
#   setup_logging(config)
#   logging.debug("Configuration: " + config)

#   # Finalize
#   print_timings

cli.add_command(build)

if __name__ == '__main__':
   cli()

