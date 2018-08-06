#!/bin/env python

import time
import os, json, requests, getpass
import argparse

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


def resume_download():
    """
    So this is a fairly unsophisticated hack of the main download script for resuming downloads from ESPA
    It could be augmented in the following ways:
    1. Remove the copy-pasta and move the common code to a different class
    2. This could be altered to include the target paths per order, although this is a significant amount of work when
    unpack_scenes does a lot of that magic for you

    """
    parser = argparse.ArgumentParser(description='Resume unfinished USGS order submission')
    parser.add_argument('target_folder', help='path to save your gzipped/tarred USGS Landsat scenes')
    parser.add_argument('jobs_file', help='file containing your ESPA order ids')
    args = parser.parse_args()
    target_folder = args.target_folder
    jobs_file = args.jobs_file
    # define an empty list
    order_ids = []

    with open(jobs_file, 'r') as filehandle:
        for line in filehandle:
            # remove linebreak which is the last character of the string
            order_id = line[:-1]

            # add item to the list
            order_ids.append(order_id)

    username = getpass.getpass(prompt='username for ESPA: ')
    password = getpass.getpass(prompt='password for ESPA: ')

    for order_id in reversed(order_ids):
        if len(order_id) > 0:
            start_check_download(order_id, target_folder, username, password)


if __name__ == '__main__':
    resume_download()
