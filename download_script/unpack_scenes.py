#!/bin/env python

import argparse
import glob
import tarfile
import os
import sys


def untar_scenes():
    parser = argparse.ArgumentParser(description='Unpack USGS Landsat scenes.')
    parser.add_argument('source_folder', help='path to your gzipped/tarred USGS Landsat scenes')
    parser.add_argument('target_folder', help='path to your ungzipped/untarred USGS Landsat scenes')
    args = parser.parse_args()
    source_folder = args.source_folder
    target_folder = args.target_folder
    tar_files = glob.glob(source_folder + '/*.tar.gz')  # a glob file containing the names of all .tar.gz
    for tar_filepath in tar_files:
        try:
            with tarfile.open(tar_filepath) as tf:
                xml = [n for n in tf.getnames() if n[-3:] == 'xml'][0]
                xml_folder = xml[10:16]
                scene_name = xml.split('.')[0]
                path_row_folder = target_folder + '/' + xml_folder
                out_folder = path_row_folder + '/' + scene_name
                print(out_folder)
                print(tar_filepath)
                if not os.path.isdir(path_row_folder):
                    os.mkdir(path_row_folder)
                try:
                    os.mkdir(out_folder)
                    tf.extractall(out_folder)
                    os.unlink(tar_filepath)
                    print('scene {0} complete'.format(str(xml)))
                except:
                    print("Oops!", sys.exc_info()[0], "occured.")
                    print('skipping: '+tar_filepath)
        except:
            print("Oops!", sys.exc_info()[0], "occured.")
            print('skipping: ' + tar_filepath)


if __name__ == '__main__':
    untar_scenes()
