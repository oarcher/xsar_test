"""
TODO: this docstring is the main xsar module documentation shown to the user. It's should be updated with some examples.
"""
import warnings
from importlib.metadata import version

__version__ = version('xsar')

import logging
from .utils import timing
import rasterio
import numpy as np
import os
import numbers
import yaml
from importlib_resources import files
from pathlib import Path
import fsspec
import aiohttp
import zipfile


def _load_config():
    """
    load config from default xsar/config.yml file or user ~/.xsar/config.yml
    Returns
    -------
    dict
    """
    user_config_file = Path('~/.xsar/config.yml').expanduser()
    default_config_file = files('xsar').joinpath('config.yml')

    if user_config_file.exists():
        config_file = user_config_file
    else:
        config_file = default_config_file

    config = yaml.load(
        config_file.open(),
        Loader=yaml.FullLoader)
    return config


config = _load_config()

from .Sentinel1 import SentinelDataset, SentinelMeta, product_info

logger = logging.getLogger('xsar')
"""
TODO: inform the user how to handle logging
"""
logger.addHandler(logging.NullHandler())

os.environ["GDAL_CACHEMAX"] = "128"


@timing
def open_dataset(*args, **kwargs):
    """
    Parameters
    ----------
    *args:
        Passed to `xsar.SentinelDataset`
    **kwargs:
        Passed to `xsar.SentinelDataset`

    Returns
    -------
    xarray.Dataset

    Notes
    -----
    xsar.open_dataset` is a simple wrapper to `xsar.SentinelDataset` that directly returns the `xarray.Dataset` object.

    >>> xsar.SentinelDataset(*args, **kwargs).dataset

    See Also
    --------
    xsar.SentinelDataset
    """
    dataset_id = args[0]
    # TODO: check product type (S1, RS2), and call specific reader
    if isinstance(dataset_id, SentinelMeta) or isinstance(dataset_id, str) and ".SAFE" in dataset_id:
        sar_obj = SentinelDataset(*args, **kwargs)
    else:
        raise TypeError("Unknown dataset type from %s" % str(dataset_id))

    return apply_cf_convention(sar_obj.dataset)


@timing
def apply_cf_convention(dataset):
    """
    Apply `CF-1.7 convention <http://cfconventions.org/Data/cf-conventions/cf-conventions-1.7/cf-conventions.html>`_ to a dataset

    Parameters
    ----------
    dataset

    Returns
    -------
    dataset wtih the cf convention
    """

    def to_cf(attr):
        if not isinstance(attr, (str, numbers.Number, np.ndarray, np.number, list, tuple)):
            return str(attr)
        else:
            return attr

    attr_dict = {
        'atrack': {
            'units': '1'
        },
        'xtrack': {
            'units': '1'
        },
        'longitude': {
            'standard_name': 'longitude',
            'units': 'degrees_east'
        },
        'latitude': {
            'standard_name': 'latitude',
            'units': 'degrees_north'
        },
        'sigma0_raw': {
            'units': 'm2/m2'
        },
        'gamma0_raw': {
            'units': 'm2/m2'
        },
    }

    for k, v in dataset.attrs.items():
        dataset.attrs[k] = to_cf(dataset.attrs[k])

    dataset.attrs['Conventions'] = 'CF-1.7'

    for key, attribute in attr_dict.items():
        for key_attr, value in attribute.items():
            if key in dataset:
                dataset[key].attrs[key_attr] = value

    return dataset


def get_test_file(fname):
    """
    get test file from  https://cyclobs.ifremer.fr/static/sarwing_datarmor/xsardata/
    file is unzipped and extracted to `config['data_dir']`

    Parameters
    ----------
    fname: str
        file name to get (without '.zip' extension)

    Returns
    -------
    str
        path to file, relative to `config['data_dir']`

    """

    res_path = config['data_dir']
    base_url = 'https://cyclobs.ifremer.fr/static/sarwing_datarmor/xsardata'
    file_url = '%s/%s.zip' % (base_url, fname)
    if not os.path.exists(os.path.join(res_path, fname)):
        warnings.warn("Downloading %s" % file_url)
        with fsspec.open(
                'filecache::%s' % file_url,
                https={'client_kwargs': {'timeout': aiohttp.ClientTimeout(total=3600)}},
                filecache={'cache_storage': os.path.join(os.path.join(config['data_dir'], 'fsspec_cache'))}
        ) as f:
            warnings.warn("Unzipping %s" % os.path.join(res_path, fname))
            with zipfile.ZipFile(f, 'r') as zip_ref:
                zip_ref.extractall(res_path)
    return os.path.join(res_path, fname)
