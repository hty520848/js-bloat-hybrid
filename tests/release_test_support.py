"""Select the imported Linux configuration for integration tests."""
import sys
import unittest

from experiments.common import ROOT, read


def release_machine():
    config = ROOT / 'config' / 'machine.frozen.json'
    if sys.platform != 'linux' or not config.is_file():
        raise unittest.SkipTest('Requires frozen inputs imported on Linux')
    return read(config)
