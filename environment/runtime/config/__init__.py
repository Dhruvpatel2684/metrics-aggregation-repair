import configparser
import os

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "resolver.ini")

def get_config():
    config = configparser.ConfigParser()
    config.read(_CONFIG_PATH)
    return config
