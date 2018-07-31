"""
:mod:`level2_order_download` - Order and download level 2 products (surface
reflectance, brightness temperature and pixel quality) from USGS.
===============================================================================

:moduleauthor: Tina Yang <tina.yang@ga.gov.au>

"""

# !/bin/env python

import argparse
import time

import logging as log
import configparser
from os.path import join as pjoin

from files import fl_start_log
from functools import wraps, reduce
import os, json, requests, getpass, gzip
import shutil
import csv

try:
    from urllib.parse import urlparse, urljoin
except ImportError:
    from urlparse import urlparse, urljoin


def download_file(url, output_dir):
    """
    Download the text archive files from USGS website to an output folder.

    :param url: USGS website
    :param output_dir: the output folder

    :returns: the downloaded file

    """

    local_filename = os.path.join(output_dir, url.split('/')[-1])
    r = requests.get(url, stream=True)
    with open(local_filename, 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:  # filter out keep-alive new chunks
                f.write(chunk)
    return local_filename


def espa_api(endpoint, verb='get', body=None, uauth=None):
    """
    A simple way suggested by USGS to interact with the ESPA Json rest API

    """

    host = 'https://espa.cr.usgs.gov/api/v1/'
    auth_tup = uauth
    response = getattr(requests, verb)(host + endpoint, auth=auth_tup, json=body)
    print('{} {}'.format(response.status_code, response.reason))
    data = response.json()

    if isinstance(data, dict):
        messages = data.pop("messages", None)
        if messages:
            print(json.dumps(messages, indent=4))
    try:
        response.raise_for_status()
    except Exception as e:
        print (e)
        return None
    else:
        return data


def check_n_download(ordered_items_to_download, order_id, data_dir, username,
                     password):
    """
    Check the individual ordered items: download if complete, otherwise keep
    checking every 5 mins

    :param ordered_items_to_download: a list of scenes to check and download
    :param order_id: the order id
    :param data_dir: folder to store downloaded data
    :param username: the username used to access espa
    :param password: the password used to access espa

    """

    print('Items to check: ' + str(len(ordered_items_to_download)))
    items_not_complete = []

    item_status_resp = espa_api('item-status/{0}'.format(order_id),
                                uauth=(username, password))
    for item in item_status_resp[order_id]:
        if item['name'] in ordered_items_to_download:
            if item['status'] == 'complete':
                dload_url = item.get('product_dload_url')
                download_file(dload_url, data_dir)
            else:
                items_not_complete.append(item['name'])

    print ('Items still pending: ' + str(len(items_not_complete)))
    if len(items_not_complete) > 0:
        time.sleep(300)
        print('check status again after 5 mins')
        check_n_download(items_not_complete, order_id, data_dir, username, password)


def start_check_download(order_id, data_dir, username, password):
    """
    Start to check the individual ordered items

    :param order_id: the order id
    :param data_dir: folder to store downloaded data
    :param username: the username used to access espa
    :param password: the password used to access espa

    """
    print('Processing order: ' + order_id)
    item_status_resp = espa_api('item-status/{0}'.format(order_id),
                                uauth=(username, password))
    print('Initial size of order:' + str(len(item_status_resp[order_id])))
    check_n_download([x['name'] for x in item_status_resp[order_id]], order_id,
                     data_dir, username, password)


def define_order(scene_list, desired_sensors_list, username, password):
    """
    Defind the order based on requsted scenes.

    :param scene_list: a list of scenes of interest
    :param desired_sensors_list: list of desired sensors
    :param username: the username used to access espa
    :param password: the password used to access espa

    :returns: the order dictionary

    """

    prod_types = ['sr', 'bt', 'pixel_qa']

    request_data = {
        'inputs': scene_list
    }

    available_products = espa_api('available-products', body=request_data,
                                  uauth=(username, password))

    filtered_order = {}

    for desired_sensor in desired_sensors_list:
        if desired_sensor in available_products:
            filtered_order[desired_sensor] = available_products[desired_sensor]

    collection = {'LT05': 'tm5_collection',
                  'LE07': 'etm7_collection',
                  'LC08': 'olitirs8_collection',
                  'LO08': 'oli8_collection'}

    # identify problem order keys and delete them from order
    problems = ['date_restricted', 'not_implemented', 'oli8_collection']
    problem_scenes = []
    for a_problem in problems:
        if a_problem in filtered_order.keys():
            if a_problem == 'date_restricted':
                problem_scenes.extend(filtered_order[a_problem]['sr'])
                print (a_problem, len(filtered_order[a_problem]['sr']))
            elif a_problem == 'not_implemented':
                print (a_problem, len(filtered_order[a_problem]))
            else:
                print (a_problem, len(filtered_order[a_problem]['inputs']))
            del filtered_order[a_problem]

    # delete problem scenes from order
    if len(problem_scenes) > 0:
        for a_problem_scene in problem_scenes:
            problem_collection = collection[a_problem_scene[:4]]
            filtered_order[problem_collection]['inputs'].remove(a_problem_scene)

    for sensor in filtered_order.keys():
        if isinstance(filtered_order[sensor], dict) and filtered_order[sensor].get('inputs'):
            filtered_order[sensor]['products'] = prod_types

    filtered_order['format'] = 'gtiff'

    return filtered_order


def submit_order(order, userNM, passWD):
    """
    Submit the defined order.

    :param order: the order dictionary
    :param userNM: the username used to access espa
    :param passWD: the password used to access espa

    :returns: the order id

    """

    print ('POST /api/v1/order')
    post_resp = espa_api('order', verb='post', body=order,
                         uauth=(userNM, passWD))
    orderid = post_resp['orderid']

    return orderid


def extract_products(fn, path_row, ymd1, ymd2):
    """
    Extract the product IDs from the USGS bulk metadata file based on spatial
    and temporal extents

    :param fn: the file name preprocessed to include only product IDs from USGS
    :param path_row: the path and row of interest
    :param ymd1: the starting date
    :param ymd2: the ending date

    """

    lines = [line.strip() for line in open(fn).readlines() if path_row in line]
    result = []
    for line in lines:
        if ymd1 <= line.split('_')[3] <= ymd2: result.append(line)
    return result


def get_latest_csv_from_usgs(csv_url, output_dir):
    """
    Download the text archive files from USGS website to an output folder and
    unzip them.

    :param csv_url: USGS website
    :param output_dir: the output folder

    :returns: the unzipped text file

    """

    local_zip_file = download_file(csv_url, output_dir)

    # unzip
    inF = gzip.open(local_zip_file, 'rb')
    print("Unzipping " + local_zip_file)
    out_file = local_zip_file.replace('.gz', '')
    outF = open((out_file), 'wb')
    outF.write(inF.read())
    inF.close()
    outF.close()

    return out_file


def produce_id_file(csv_url, root_folder, product_id_filename):
    """
    Download the text archive files from USGS websites for all landsats to an
    output folder, unzip them, and produce a simplified csv file with only
    product id combining all the landsats.

    :param csv_url: a list of USGS website
    :param root_folder: the output folder
    :param product_id_filename: the target name of the product id list

    :returns: the produced product id file

    """

    csv_list = []
    for a_csv_url in csv_url:
        a_csv = get_latest_csv_from_usgs(a_csv_url, root_folder)
        csv_list.append(a_csv)

    output_csv = pjoin(root_folder, product_id_filename)

    handles = [open(a_csv, 'r') for a_csv in csv_list]
    readers = [csv.reader(f, delimiter=',') for f in handles]

    with open(output_csv, 'w') as h:
        writer = csv.writer(h, delimiter=',', lineterminator='\n')
        writer.writerow(['LANDSAT_PRODUCT_ID'])
        i = 0
        for reader in readers:
            for row in reader:
                if i == 0:
                    # ls5
                    id_field = 26
                elif i == 1:
                    # ls7
                    id_field = 29
                else:
                    # ls8
                    id_field = 31

                if row[id_field][-2:] != 'RT' and row[id_field] != 'LANDSAT_PRODUCT_ID':
                    writer.writerow([row[id_field]])
            i += 1

    for f in handles:
        f.close()
    print('Saved LANDSAT bulk metadata in: ' + output_csv)
    return output_csv


def create_sub_output_folder(root, sub_folder):
    """
    Create a subfolder under a given folder.

    :param root: `string` Name of root directory
    :param sub_folder: `string` Name of subfolder
    :raises OSError: If the directory tree cannot be created.

    :returns: the path of created subfolder

    """

    output = pjoin(root, sub_folder)

    if os.path.exists(output):
        shutil.rmtree(output)
    try:
        os.makedirs(output)
    except OSError:
        raise

    return output


def timer(f):
    """
    Basic timing functions for entire process
    """

    @wraps(f)
    def wrap(*args, **kwargs):
        """
        Wrap
        """

        t1 = time.time()
        res = f(*args, **kwargs)

        tottime = time.time() - t1
        msg = "%02d:%02d:%02d " % \
              reduce(lambda ll, b: divmod(ll[0], b) + ll[1:],
                     [(tottime,), 60, 60])

        log.info("Time for {0}:{1}".format(f.__name__, msg))
        return res

    return wrap


@timer
def run():
    """
    Run the program

    """

    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config_file', help='The configuration file')
    args = parser.parse_args()
    configFile = args.config_file

    config = configparser.RawConfigParser()
    config.read(configFile)

    download_catalogue = config.getboolean('Process', 'download_catalogue')
    product_id_filename = config.get('Process', 'product_id_filename')
    desired_sensors_list = config.get('Process', 'desired_sensors_list').split(' ')
    date_range_list = config.get('Process', 'date_range_list').split(' ')
    path_row_list = config.get('Process', 'path_row_list').split(' ')
    root_folder = config.get('Process', 'root_folder')

    csv_url = ['https://landsat.usgs.gov/landsat/metadata_service/'
               'bulk_metadata_files/LANDSAT_TM_C1.csv.gz',
               'https://landsat.usgs.gov/landsat/metadata_service/'
               'bulk_metadata_files/LANDSAT_ETM_C1.csv.gz',
               'https://landsat.usgs.gov/landsat/metadata_service/'
               'bulk_metadata_files/LANDSAT_8_C1.csv.gz']

    if download_catalogue:
        print('downloading latest LANDSAT bulk metadata file')
        product_id_path = produce_id_file(csv_url, root_folder, product_id_filename)
    else:
        print('skipping download of latest LANDSAT metadata file')
        product_id_path = pjoin(root_folder, product_id_filename)

    logfile = config.get('Logging', 'LogFile')
    loglevel = config.get('Logging', 'LogLevel')
    verbose = config.getboolean('Logging', 'Verbose')

    fl_start_log(logfile, loglevel, verbose)
    log.info("start ...")

    username = getpass.getpass(prompt='username for ESPA: ')
    password = getpass.getpass(prompt='password for ESPA: ')

    order_id_path_list = []

    for path_row in path_row_list:
        data_dir = pjoin(root_folder, 'L2/gz/{}'.format(path_row))
        if not os.path.exists(data_dir):
            data_dir = create_sub_output_folder(root_folder,
                                                'L2/gz/{}'.format(path_row))

        for date_range in date_range_list:
            date_start = date_range.split('_')[0]
            date_end = date_range.split('_')[1]
            product_list = extract_products(product_id_path, path_row,
                                            date_start, date_end)
            order = define_order(product_list, desired_sensors_list, username, password)
            order_no = 0
            found_sensors = []
            for sensor in desired_sensors_list:
                if sensor in order:
                    found_sensors.append(sensor)
                    order_no += len(order[sensor]['inputs'])
            if len(found_sensors) > 0:
                print ('ordering  ' + str(order_no) + ' scenes(s) for path/row: ' + path_row + ', date range: ' +
                       date_range + ', sensors: ' + str(found_sensors))
                order_id = submit_order(order, username, password)
                order_id_path_list.append((order_id, data_dir))
            else:
                print('No items found for for path/row: ' + path_row + ', date range: ' + date_range + ', sensors: ' +
                      str(desired_sensors_list))

    for order_id_path in order_id_path_list:
        start_check_download(order_id_path[0], order_id_path[1], username, password)

    log.info("Successfully completed!")


if __name__ == '__main__':
    run()
