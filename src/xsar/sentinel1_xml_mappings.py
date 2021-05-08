"""
xpath mapping from xml file, with convertion functions
"""

from datetime import datetime
import numpy as np
from scipy.interpolate import RectBivariateSpline, interp1d
from shapely.geometry import box
import pandas as pd
import xarray as xr
import warnings
import geopandas as gpd
from shapely.geometry import Polygon
import os.path

namespaces = {
    "xfdu": "urn:ccsds:schema:xfdu:1",
    "s1sarl1": "http://www.esa.int/safe/sentinel-1.0/sentinel-1/sar/level-1",
    "s1sar": "http://www.esa.int/safe/sentinel-1.0/sentinel-1/sar",
    "s1": "http://www.esa.int/safe/sentinel-1.0/sentinel-1",
    "safe": "http://www.esa.int/safe/sentinel-1.0",
    "gml": "http://www.opengis.net/gml"
}

# xpath convertion function: they take only one args (list returned by xpath)
scalar = lambda x: x[0]
scalar_float = lambda x: float(x[0])
date_converter = lambda x: datetime.strptime(x[0], '%Y-%m-%dT%H:%M:%S.%f')
datetime64_array = lambda x: np.array([np.datetime64(date_converter([sx])) for sx in x])
int_1Darray_from_string = lambda x: np.fromstring(x[0], dtype=int, sep=' ')
float_2Darray_from_string_list = lambda x: np.vstack([np.fromstring(e, dtype=float, sep=' ') for e in x])
int_1Darray_from_join_strings = lambda x: np.fromstring(" ".join(x), dtype=int, sep=' ')
float_1Darray_from_join_strings = lambda x: np.fromstring(" ".join(x), dtype=float, sep=' ')
int_array = lambda x: np.array(x, dtype=int)
uniq_sorted = lambda x: np.array(sorted(set(x)))
ordered_category = lambda x:  pd.Categorical(x).reorder_categories(x,ordered=True)
normpath = lambda paths: [ os.path.normpath(p) for p in paths ]

def or_ipf28(xpath):
    """change xpath to match ipf <2.8 or >2.9 (for noise range)"""
    xpath28 = xpath.replace('noiseRange', 'noise').replace('noiseAzimuth', 'noise')
    if xpath28 != xpath:
        xpath += " | %s" % xpath28
    return xpath

def list_poly_from_list_string_coords(str_coords_list):
    footprints = []
    for gmlpoly in str_coords_list:
        footprints.append(Polygon(
            [(float(lon), float(lat)) for lat, lon in [latlon.split(",")
                                                       for latlon in gmlpoly.split(" ")]]))
    return footprints

# xpath_mappings:
# first level key is xml file type
# second level key is variable name
# mappings may be 'xpath', or 'tuple(func,xpath)', or 'dict'
#  - xpath is an lxml xpath
#  - func is a decoder function fed by xpath
#  - dict is a nested dict, to create more hierarchy levels.
xpath_mappings = {
    "manifest": {
        'ipf_version': (scalar_float, '//xmlData/safe:processing/safe:facility/safe:software/@version'),
        'swath_type': (scalar, '//s1sarl1:instrumentMode/s1sarl1:mode'),
        'polarizations': (ordered_category, '//s1sarl1:standAloneProductInformation/s1sarl1:transmitterReceiverPolarisation'),
        'footprints': (list_poly_from_list_string_coords, '//safe:frame/safe:footPrint/gml:coordinates'),
        'product_type': (scalar, '//s1sarl1:standAloneProductInformation/s1sarl1:productType'),
        'mission': (scalar, '//safe:platform/safe:familyName'),
        'satellite': (scalar, '//safe:platform/safe:number'),
        'start_date': (date_converter, '//safe:acquisitionPeriod/safe:startTime'),
        'stop_date': (date_converter, '//safe:acquisitionPeriod/safe:stopTime'),
        'annotation_files': (normpath, '/xfdu:XFDU/dataObjectSection/*[@repID="s1Level1ProductSchema"]/byteStream/fileLocation/@href'),
        'measurement_files': (normpath, '/xfdu:XFDU/dataObjectSection/*[@repID="s1Level1MeasurementSchema"]/byteStream/fileLocation/@href'),
        'noise_files': (normpath, '/xfdu:XFDU/dataObjectSection/*[@repID="s1Level1NoiseSchema"]/byteStream/fileLocation/@href'),
        'calibration_files': (normpath, '/xfdu:XFDU/dataObjectSection/*[@repID="s1Level1CalibrationSchema"]/byteStream/fileLocation/@href')
    },
    'calibration': {
        'polarization': (scalar, '/calibration/adsHeader/polarisation'),
        # 'number_of_vector': '//calibration/calibrationVectorList/@count',
        'atrack': (np.array, '//calibration/calibrationVectorList/calibrationVector/line'),
        'xtrack': (int_1Darray_from_string, '//calibration/calibrationVectorList/calibrationVector[1]/pixel'),
        'sigma0_lut': (
            float_2Darray_from_string_list, '//calibration/calibrationVectorList/calibrationVector/sigmaNought'),
        'gamma0_lut': (float_2Darray_from_string_list, '//calibration/calibrationVectorList/calibrationVector/gamma')
    },
    'noise': {
        'polarization': (scalar, '/noise/adsHeader/polarisation'),
        'range': {
            'atrack': (int_array, or_ipf28('/noise/noiseRangeVectorList/noiseRangeVector/line')),
            'xtrack': (lambda x: [np.fromstring(s, dtype=int, sep=' ') for s in x],
                       or_ipf28('/noise/noiseRangeVectorList/noiseRangeVector/pixel')),
            'noiseLut': (
                lambda x: [np.fromstring(s, dtype=float, sep=' ') for s in x],
                or_ipf28('/noise/noiseRangeVectorList/noiseRangeVector/noiseRangeLut'))
        },
        'azi': {
            'swath': '/noise/noiseAzimuthVectorList/noiseAzimuthVector/swath',
            'atrack': (lambda x: [np.fromstring(str(s), dtype=int, sep=' ') for s in x],
                       '/noise/noiseAzimuthVectorList/noiseAzimuthVector/line'),
            'atrack_start': (int_array, '/noise/noiseAzimuthVectorList/noiseAzimuthVector/firstAzimuthLine'),
            'atrack_stop': (int_array, '/noise/noiseAzimuthVectorList/noiseAzimuthVector/lastAzimuthLine'),
            'xtrack_start': (int_array, '/noise/noiseAzimuthVectorList/noiseAzimuthVector/firstRangeSample'),
            'xtrack_stop': (int_array, '/noise/noiseAzimuthVectorList/noiseAzimuthVector/lastRangeSample'),
            'noiseLut': (
                lambda x: [np.fromstring(str(s), dtype=float, sep=' ') for s in x],
                '/noise/noiseAzimuthVectorList/noiseAzimuthVector/noiseAzimuthLut'),
        }
    },
    'annotation': {
        'atrack': (uniq_sorted, '/product/geolocationGrid/geolocationGridPointList/geolocationGridPoint/line'),
        'xtrack': (uniq_sorted, '/product/geolocationGrid/geolocationGridPointList/geolocationGridPoint/pixel'),
        'incidence': (
            np.array, '/product/geolocationGrid/geolocationGridPointList/geolocationGridPoint/incidenceAngle'),
        'elevation': (
            np.array, '/product/geolocationGrid/geolocationGridPointList/geolocationGridPoint/elevationAngle'),
        'polarization': (scalar, '/product/adsHeader/polarisation'),
        'atrack_time_range': (
            datetime64_array, '/product/imageAnnotation/imageInformation/*[contains(name(),"LineUtcTime")]'),
        'denoised': (scalar, '/product/imageAnnotation/processingInformation/thermalNoiseCorrectionPerformed'),
        'pol': (scalar, '/product/adsHeader/polarisation'),
        'pass': (scalar, '/product/generalAnnotation/productInformation/pass'),
        'platform_heading': (scalar_float, '/product/generalAnnotation/productInformation/platformHeading')
    }
}


# compounds variables converters

def signal_lut(atrack, xtrack, lut):
    lut_f = RectBivariateSpline(atrack, xtrack, lut, kx=1, ky=1)
    return lut_f



class _NoiseLut:
    """small internal class that return a lut function(atracks, xtracks) defined on all the image, from blocks in the image"""

    def __init__(self, blocks):
        self.blocks = blocks

    def __call__(self, atracks, xtracks):
        """ return noise[a.size,x.size], by finding the intersection with blocks and calling the corresponding block.lut_f"""
        if len(self.blocks) == 0:
            # no noise (ie no azi noise for ipf < 2.9)
            return 1
        else:
            # the array to be returned
            noise = xr.DataArray(
                np.ones((atracks.size, xtracks.size)) * np.nan,
                dims=('atrack', 'xtrack'),
                coords={'atrack': atracks, 'xtrack': xtracks}
            )
            # find blocks that intersects with asked_box
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                # the box coordinates of the returned array
                asked_box = box(max(0, atracks[0] - 0.5), max(0, xtracks[0] - 0.5), atracks[-1] + 0.5,
                                xtracks[-1] + 0.5)
                # set match_blocks as the non empty intersection with asked_box
                match_blocks = self.blocks.copy()
                match_blocks.geometry = self.blocks.geometry.intersection(asked_box)
                match_blocks = match_blocks[~match_blocks.is_empty]
            for i, block in match_blocks.iterrows():
                (sub_a_min, sub_x_min, sub_a_max, sub_x_max) = map(int, block.geometry.bounds)
                sub_a = atracks[(atracks >= sub_a_min) & (atracks <= sub_a_max)]
                sub_x = xtracks[(xtracks >= sub_x_min) & (xtracks <= sub_x_max)]
                noise.loc[dict(atrack=sub_a, xtrack=sub_x)] = block.lut_f(sub_a, sub_x)

        # values returned as np array
        return noise.values

def noise_lut_range(atracks, xtracks, noiseLuts):
    """

    Parameters
    ----------
    atracks: np.ndarray
        1D array of atracks. lut is defined at each atrack
    xtracks: list of np.ndarray
        arrays of xtracks. list length is same as xtracks. each array define xtracks where lut is defined
    noiseLuts: list of np.ndarray
        arrays of luts. Same structure as xtarcks.

    Returns
    -------
    geopandas.GeoDataframe
        noise range geometry.
        'geometry' is the polygon where 'lut_f' is defined.
        attrs['type'] set to 'xtrack'


    """

    class Lut_box_range:
        def __init__(self, a_start, a_stop, x, l):
            self.atracks = np.arange(a_start, a_stop)
            self.xtracks = x
            self.area = box(a_start, x[0], a_stop, x[-1])
            self.lut_f = interp1d(x, l, kind='linear', fill_value=np.nan, assume_sorted=True, bounds_error=False)

        def __call__(self, atracks, xtracks):
            lut = np.tile(self.lut_f(xtracks), (atracks.size, 1))
            return lut

    blocks = []
    # atracks is where lut is defined. compute atracks interval validity
    atracks_start = (atracks - np.diff(atracks, prepend=0) / 2).astype(int)
    atracks_stop = np.ceil(atracks + np.diff(atracks, append=atracks[-1] + 1) / 2).astype(
        int)  # end is not included in the interval
    for a_start, a_stop, x, l in zip(atracks_start, atracks_stop, xtracks, noiseLuts):
        lut_f = Lut_box_range(a_start, a_stop, x, l)
        block = pd.Series(dict([
            ('lut_f', lut_f),
            ('geometry', lut_f.area)]))
        blocks.append(block)

    # to geopandas
    blocks = pd.concat(blocks, axis=1).T
    blocks = gpd.GeoDataFrame(blocks)

    return _NoiseLut(blocks)


def noise_lut_azi(atrack_azi, atrack_azi_start,
                  atrack_azi_stop,
                  xtrack_azi_start, xtrack_azi_stop, noise_azi_lut, swath):
    """

    Parameters
    ----------
    atrack_azi
    atrack_azi_start
    atrack_azi_stop
    xtrack_azi_start
    xtrack_azi_stop
    noise_azi_lut
    swath

    Returns
    -------
    geopandas.GeoDataframe
        noise range geometry.
        'geometry' is the polygon where 'lut_f' is defined.
        attrs['type'] set to 'atrack'
    """

    class Lut_box_azi:
        def __init__(self, sw, a, a_start, a_stop, x_start, x_stop, lut):
            self.atracks = a
            self.xtracks = np.arange(x_start, x_stop + 1)
            self.area = box(max(0, a_start - 0.5), max(0, x_start - 0.5), a_stop + 0.5, x_stop + 0.5)
            if len(lut) > 1:
                self.lut_f = interp1d(a, lut, kind='linear', fill_value=np.nan, assume_sorted=True, bounds_error=False)
            else:
                # not enought values to do interpolation
                # noise will be constant on this box!
                self.lut_f = lambda _a: lut

        def __call__(self, atracks, xtracks):
            return np.tile(self.lut_f(atracks), (xtracks.size, 1)).T

    blocks = []
    for sw, a, a_start, a_stop, x_start, x_stop, lut in zip(swath, atrack_azi, atrack_azi_start, atrack_azi_stop,
                                                            xtrack_azi_start,
                                                            xtrack_azi_stop, noise_azi_lut):
        lut_f = Lut_box_azi(sw, a, a_start, a_stop, x_start, x_stop, lut)
        block = pd.Series(dict([
            ('lut_f', lut_f),
            ('geometry', lut_f.area)]))
        blocks.append(block)

    if len(blocks) == 0:
        # no azi noise (ipf < 2.9) or WV
        blocks.append(pd.Series(dict([
            ('atracks', np.array([])),
            ('xtracks', np.array([])),
            ('lut_f', lambda a, x: 1),
            ('geometry', box(0, 0, 65535, 65535))])))  # arbitrary large box (bigger than whole image)

    # to geopandas
    blocks = pd.concat(blocks, axis=1).T
    blocks = gpd.GeoDataFrame(blocks)

    return _NoiseLut(blocks)

def annotation_angle(atrack, xtrack, angle):
    lut = angle.reshape(atrack.size, xtrack.size)
    lut_f = RectBivariateSpline(atrack, xtrack, lut, kx=1, ky=1)
    return lut_f

def datetime64_array(dates):
    """list of datetime to np.datetime64 array"""
    return np.array([np.datetime64(d) for d in dates])

def df_files(annotation_files, measurement_files, noise_files, calibration_files):
    # get polarizations and file number from filename
    pols = [ os.path.basename(f).split('-')[3].upper() for f in annotation_files ]
    num = [ int(os.path.splitext(os.path.basename(f))[0].split('-')[8]) for f in annotation_files ]
    dsid = [ os.path.basename(f).split('-')[1].upper() for f in annotation_files ]

    # check that dsid are spatialy uniques (i.e. there is only one dsid per geographic position)
    # some SAFES like WV, dsid are not uniques ('WV1' and 'WV2')
    # we want them uniques, and compatibles with gdal sentinel driver (ie 'WV_012')
    pols_count = len(set(pols))
    subds_count = len(annotation_files) // pols_count
    dsid_count = len(set(dsid))
    if dsid_count != subds_count:
        dsid_rad = dsid[0][:-1]  # WV
        dsid = [ "%s_%03d" % (dsid_rad, n) for n in num]
        assert len(set(dsid)) == subds_count  # probably an unknown mode we need to handle

    df = pd.DataFrame(
        {
            'polarization': pols,
            'dsid': dsid,
            'annotation': annotation_files,
            'measurement': measurement_files,
            'noise': noise_files,
            'calibration': calibration_files
        },
        index=num
    )
    return df

# dict of compounds variables.
# compounds variables are variables composed of several variables.
# the key is the variable name, and the value is a python structure,
# where leaves are jmespath in xpath_mappings
compounds_vars = {
    'safe_attributes': {
        'ipf_version': 'manifest.ipf_version',
        'swath_type': 'manifest.swath_type',
        'polarizations': 'manifest.polarizations',
        'product_type': 'manifest.product_type',
        'mission': 'manifest.mission',
        'satellite': 'manifest.satellite',
        'start_date': 'manifest.start_date',
        'stop_date': 'manifest.stop_date',
        'footprints': 'manifest.footprints'
    },
    'files': {
        'func': df_files,
        'args': ('manifest.annotation_files', 'manifest.measurement_files', 'manifest.noise_files', 'manifest.calibration_files')
    },
    'sigma0_lut': {
        'func': signal_lut,
        'args': ('calibration.atrack', 'calibration.xtrack', 'calibration.sigma0_lut')
    },
    'gamma0_lut': {
        'func': signal_lut,
        'args': ('calibration.atrack', 'calibration.xtrack', 'calibration.gamma0_lut')
    },
    'noise_lut_range': {
        'func': noise_lut_range,
        'args': ('noise.range.atrack', 'noise.range.xtrack', 'noise.range.noiseLut')
    },
    'noise_lut_azi': {
        'func': noise_lut_azi,
        'args': (
            'noise.azi.atrack', 'noise.azi.atrack_start', 'noise.azi.atrack_stop',
            'noise.azi.xtrack_start',
            'noise.azi.xtrack_stop', 'noise.azi.noiseLut',
            'noise.azi.swath')
    },
    'denoised': ('annotation.pol', 'annotation.denoised'),
    'incidence': {
        'func': annotation_angle,
        'args': ('annotation.atrack', 'annotation.xtrack', 'annotation.incidence')
    },
    'elevation': {
        'func': annotation_angle,
        'args': ('annotation.atrack', 'annotation.xtrack', 'annotation.elevation')
    },
}
