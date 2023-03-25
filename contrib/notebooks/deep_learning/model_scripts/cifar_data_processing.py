# Copyright (c) Microsoft. All rights reserved.

# Licensed under the MIT license. See LICENSE.md file in the project root
# for full license information.
# ==============================================================================


from __future__ import print_function

import argparse

try:
    from urllib.request import urlretrieve 
except ImportError: 
    from urllib import urlretrieve
import sys
import tarfile
import os
import numpy as np
import pickle as cp
from PIL import Image
import xml.etree.cElementTree as et
import xml.dom.minidom
from itertools import product, count

IMGSIZE = 32
NUMBER_OF_TRAINING_BATCHES = 5
CIFAR_URL = 'http://www.cs.toronto.edu/~kriz/cifar-10-python.tar.gz'


def download_data(src):
    print ('Downloading ' + src)
    fname, h = urlretrieve(src, './delete.me')
    print ('Done.')
    return fname


def extract(fname):
    try:
        print ('Extracting files...')
        with tarfile.open(fname) as tar:
            def is_within_directory(directory, target):
                
                abs_directory = os.path.abspath(directory)
                abs_target = os.path.abspath(target)
            
                prefix = os.path.commonprefix([abs_directory, abs_target])
                
                return prefix == abs_directory
            
            def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
            
                for member in tar.getmembers():
                    member_path = os.path.join(path, member.name)
                    if not is_within_directory(path, member_path):
                        raise Exception("Attempted Path Traversal in Tar File")
            
                tar.extractall(path, members, numeric_owner=numeric_owner) 
                
            
            safe_extract(tar)
        print ('Done.')
    finally:
        os.remove(fname)


def _pad_image(pixData, pad):
    return np.pad(pixData, ((0, 0), (pad, pad), (pad, pad)), mode='constant', constant_values=128) # can also use mode='edge'


def saveMean(fname, data):
    root = et.Element('opencv_storage')
    et.SubElement(root, 'Channel').text = '3'
    et.SubElement(root, 'Row').text = str(IMGSIZE)
    et.SubElement(root, 'Col').text = str(IMGSIZE)
    meanImg = et.SubElement(root, 'MeanImg', type_id='opencv-matrix')
    et.SubElement(meanImg, 'rows').text = '1'
    et.SubElement(meanImg, 'cols').text = str(IMGSIZE * IMGSIZE * 3)
    et.SubElement(meanImg, 'dt').text = 'f'
    et.SubElement(meanImg, 'data').text = ' '.join(['%e' % n for n in np.reshape(data, (IMGSIZE * IMGSIZE * 3))])

    tree = et.ElementTree(root)
    tree.write(fname)
    x = xml.dom.minidom.parse(fname)
    with open(fname, 'w') as f:
        f.write(x.toprettyxml(indent = '  '))


def saveImage(fname, pixData, pad):
    if pad > 0:
        pixData = _pad_image(pixData, pad)

    img = Image.new('RGB', (IMGSIZE + 2 * pad, IMGSIZE + 2 * pad))
    pixels = img.load()
    for x, y in product(range(img.size[0]), range(img.size[1])):
        pixels[x, y] = (pixData[0][y][x], pixData[1][y][x], pixData[2][y][x])
    img.save(fname)


def load_data_file(f):
    if sys.version_info[0] < 3: # python 3
        data = cp.load(f)
    else: 
        data = cp.load(f, encoding='latin1')
    return data['labels'], data['data'] 


def read_train_batch(frompath, batch_index):
    return read_batch(os.path.join(frompath, "data_batch_{}".format(batch_index)))


def read_test_batch(frompath):
    return read_batch(os.path.join(frompath, "test_batch"))


def read_batch(filename):    
    with open(filename, 'rb') as f:
        labels, data = load_data_file(f)
        for i in range(len(labels)):
            yield labels[i], data[i, :].reshape((3, IMGSIZE, IMGSIZE))


def saveTrainImages(topath, map_filename='train_map.txt', mean_filename='CIFAR-10_mean.xml', frompath='cifar-10-batches-py'):   
    if not os.path.exists(topath):
        os.makedirs(topath)
    
    file_num_generator = count(start=0, step=1)
    dataSum = np.zeros((3, IMGSIZE, IMGSIZE)) # mean is in CHW format.
    with open(map_filename, 'w') as mapFile:
        for ifile in range(1, NUMBER_OF_TRAINING_BATCHES+1): # Loop through batches
            for label, data in read_train_batch(frompath, ifile):
                fname = '%05d.png' % next(file_num_generator)
                saveImage(os.path.join(topath, fname), data, 4)
                mapFile.write("%s\t%d\n" % (fname, label))
                dataSum+=data
    saveMean(mean_filename, dataSum / next(file_num_generator))


def saveTestImages(topath, filename='test_map.txt', frompath='cifar-10-batches-py'):
    if not os.path.exists(topath):
        os.makedirs(topath)
    
    file_num_generator = count(start=0, step=1)
    with open(filename, 'w') as mapFile:
        for label, data in read_test_batch(frompath):
            fname = '%05d.png' % next(file_num_generator)
            saveImage(os.path.join(topath, fname), data, 4)
            mapFile.write("%s\t%d\n" % (fname, label))


if __name__=="__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--datadir', required=True)
    args = vars(parser.parse_args())

    fname = download_data(CIFAR_URL)
    extract(fname)
    train_path = os.path.join(args['datadir'], 'train')
    test_path = os.path.join(args['datadir'], 'test')
    saveTrainImages(train_path,
                    map_filename=os.path.join(args['datadir'], 'train_map.txt'),
                    mean_filename=os.path.join(args['datadir'], 'CIFAR-10_mean.xml'))
    saveTestImages(test_path, os.path.join(args['datadir'], 'test_map.txt'))