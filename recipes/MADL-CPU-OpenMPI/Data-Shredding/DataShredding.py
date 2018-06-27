from __future__ import print_function
import json
import os
import sys
from azure.storage.blob import BlockBlobService
from os import listdir
from os.path import isfile, join


# make sure config data is encode it correctly
def encode(value):
    if isinstance(value, type('str')):
        return value
    return value.encode('utf-8')


# configuration class
class Configuration:

    def __init__(self, file_name):
        if not os.path.exists(file_name):
            raise ValueError('Cannot find configuration file "{0}"'.
                             format(file_name))

        with open(file_name, 'r') as f:
            conf = json.load(f)

        try:
            self.node_count = encode(conf['node_count'])
            self.thread_count = encode(conf['thread_count'])
            self.training_data_shred_count = encode(conf['training_data_shred_count'])
            self.dataset_local_directory = encode(conf['dataset_local_directory'])
            self.shredded_dataset_local_directory = encode(conf['shredded_dataset_local_directory'])
            self.shredded_dataset_Per_Node = encode(conf['shredded_dataset_Per_Node'])
            self.container_name = encode(conf['container_name'])
            self.trainind_dataset_name = encode(conf['trainind_dataset_name'])
            self.training_data_container_name = encode(conf['training_data_container_name'])
            self.subscription_id = encode(conf['subscription_id'])
            self.secret_key = encode(conf['secret_key'])
            self.resource_group = encode(conf['resource_group'])
            self.storage_account_name = encode(conf['storage_account']['name'])
            self.storage_account_key = encode(conf['storage_account']['key'])
        except KeyError as err:
            raise AttributeError('Please provide a value for "{0}" configuration key'.format(err.args[0]))


# load the configuration data
cfg = Configuration('configuration.json')

# azure block service object
blob_service = BlockBlobService(cfg.storage_account_name, cfg.storage_account_key)

# container name
azure_blob_container_name = cfg.container_name

# training data container name
azure_blob_training_data_container_name = cfg.training_data_container_name

# create the container that will host the data blobs
blob_service.create_container(azure_blob_container_name, fail_on_exist=False)


# the function that load the data from the training blob, partition the data
# and upload it to the container blobs
def partition_and_upload_dataset_to_blob(blob_service, azure_blob_container_name):

    # List the blobs in a training container
    blobs = []
    marker = None
    blobs_size = 1
    while True:
        batch = blob_service.list_blobs(azure_blob_training_data_container_name, marker=marker)
        blobs.extend(batch)
        if not batch.next_marker:
            break
        marker = batch.next_marker
    for blob in blobs:
        blobs_size += blob.properties.content_length
        print(blob.name)

    # the vm / thread count
    vm_thread_count = (int(cfg.node_count) - 1) * int(cfg.thread_count)

    # the file count per vm
    file_count = int(cfg.training_data_shred_count) // vm_thread_count

    # the file size
    file_size = blobs_size // int(cfg.training_data_shred_count)

    # data path directory
    dataset_local_directory = os.path.normpath(cfg.dataset_local_directory)

    # local shredded data directory
    shredded_dataset_local_directory = os.path.normpath(cfg.shredded_dataset_local_directory)
    shredded_dataset_Per_Node = os.path.normpath(cfg.shredded_dataset_Per_Node)

    # download data from training blob, slice it
    print('downloading dataset from blob and create them localy...')
    i = 0
    for itr in range(len(blobs)):
        blob = blobs[itr]
        blob_service.get_blob_to_path(
            azure_blob_training_data_container_name,
            blob.name, os.path.join(dataset_local_directory, blob.name))
        file_name_no_extension, file_extension = os.path.splitext(blob.name)

        lines_bytes_size = 0
        alist = []
        with open(os.path.join(dataset_local_directory, blob.name), 'r') as in_file:
            for line in in_file:
                lines_bytes_size += sys.getsizeof(line)
                alist.append(line)
                if(lines_bytes_size >= file_size):
                    with open(os.path.join(
                            shredded_dataset_local_directory,
                            file_name_no_extension + '_' + str(itr) + '_' + str(i) + file_extension), 'w') as wr:
                        for item in alist:
                            wr.write(item)
                        lines_bytes_size = 0
                        alist = []
                        i += 1

    # combine shreded files into a one file per node
    alldatafiles = [f for f in listdir(shredded_dataset_local_directory) if isfile(join(shredded_dataset_local_directory, f))]
    low_index = 0
    high_index = file_count
    filename = "data.lst"
    for vm_count in range(vm_thread_count):
        blob_name = cfg.trainind_dataset_name + "-" + "%05d" % (vm_count,)
        if(high_index > len(alldatafiles)):
            high_index = len(alldatafiles)
        if not os.path.exists(os.path.join(shredded_dataset_Per_Node, blob_name)):
            os.makedirs(os.path.join(shredded_dataset_Per_Node, blob_name))
        with open(os.path.join(shredded_dataset_Per_Node, blob_name + '\\' + filename), 'w') as outfile:
            for itr in range(low_index, high_index):
                    with open(os.path.join(shredded_dataset_local_directory, alldatafiles[itr])) as infile:
                        for line in infile:
                            outfile.write(line)
        low_index += file_count
        high_index += file_count

    # upload combined sliced data to blobs
    for subdir, dirs, files in os.walk(shredded_dataset_Per_Node):
        for file in files:
            print(os.path.basename(subdir))
            print(os.path.join(subdir, file))
            blob_service.create_blob_from_path(azure_blob_container_name, os.path.basename(subdir) + '/' + file, os.path.join(subdir, file))

    print('Done')


# begin loading, partitioning and deploying training data
partition_and_upload_dataset_to_blob(blob_service, azure_blob_container_name)
