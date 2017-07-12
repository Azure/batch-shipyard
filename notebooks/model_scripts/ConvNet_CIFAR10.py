# Copyright (c) Microsoft. All rights reserved.

# Licensed under the MIT license. See LICENSE.md file in the project root
# for full license information.
# ==============================================================================

from __future__ import print_function

import _cntk_py
import argparse
import json
import logging
import os
from uuid import uuid4

import cntk
import cntk.io.transforms as xforms
import numpy as np
from cntk import layers, Trainer, learning_rate_schedule, momentum_as_time_constant_schedule, momentum_sgd, \
    UnitType, CrossValidationConfig
from cntk.io import MinibatchSource, ImageDeserializer, StreamDef, StreamDefs
from cntk.logging import ProgressPrinter, TensorBoardProgressWriter
from cntk.losses import cross_entropy_with_softmax
from cntk.metrics import classification_error
from cntk.ops import minus, element_times, constant, relu

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


_ABS_PATH   = os.getcwd()
_MODEL_PATH = os.path.join(_ABS_PATH, "Models")

# model dimensions
_IMAGE_HEIGHT = 32
_IMAGE_WIDTH  = 32
_NUM_CHANNELS = 3  # RGB
_NUM_CLASSES  = 10
_MODEL_NAME   = "ConvNet_CIFAR10_model.dnn"
_EPOCH_SIZE = 50000


def process_map_file(map_file, imgfolder):
    """ Convert map file format to one required by CNTK ImageDeserializer
    """
    logger.info('Processing {}...'.format(map_file))
    orig_file = open(map_file, 'r')
    map_path, map_name = os.path.split(map_file)
    new_filename = os.path.join(map_path, 'p_{}'.format(map_name))
    new_file = open(new_filename, 'w')
    for line in orig_file:
        fname, label = line.split('\t')
        new_file.write("%s\t%s\n" % (os.path.join(imgfolder, fname), label.strip()))
    orig_file.close()
    new_file.close()
    return new_filename


def _create_env_variable_appender(env_var_name):
    def env_var_appender(identifier):
        env_var_value = os.environ.get(env_var_name, None)
        if env_var_value is None:
            return identifier
        else:
            return '{}_{}'.format(identifier, env_var_value)
    return env_var_appender


_append_task_id = _create_env_variable_appender('AZ_BATCH_TASK_ID') # Append task id if the env variable exists
_append_job_id = _create_env_variable_appender('AZ_BATCH_JOB_ID')   # Append job id if the env variable exists


def _get_unique_id():
    """ Returns a unique identifier

    If executed in a batch environment it will incorporate the job and task id
    """
    return _append_job_id(_append_task_id(str(uuid4())[:8]))


def _save_results(test_result, filename, **kwargs):
    results_dict = {'test_metric':test_result, 'parameters': kwargs}
    logger.info('Saving results {}'.format(results_dict))

    if not os.path.exists(os.path.dirname(filename)):
        os.makedirs(os.path.dirname(filename))

    with open(filename, 'w') as outfile:
        json.dump(results_dict, outfile)


def create_image_mb_source(map_file, mean_file, train, total_number_of_samples):
    """ Creates minibatch source
    """
    if not os.path.exists(map_file) or not os.path.exists(mean_file):
        raise RuntimeError(
            "File '%s' or '%s' does not exist. " %
            (map_file, mean_file))

    # transformation pipeline for the features has jitter/crop only when training
    transforms = []
    if train:
        imgfolder = os.path.join(os.path.split(map_file)[0], 'train')
        transforms += [
            xforms.crop(crop_type='randomside', side_ratio=0.8, jitter_type='uniratio')  # train uses jitter
        ]
    else:
        imgfolder = os.path.join(os.path.split(map_file)[0], 'test')

    transforms += [
        xforms.scale(width=_IMAGE_WIDTH, height=_IMAGE_HEIGHT, channels=_NUM_CHANNELS, interpolations='linear'),
        xforms.mean(mean_file)
    ]

    map_file = process_map_file(map_file, imgfolder)

    # deserializer
    return MinibatchSource(
        ImageDeserializer(map_file, StreamDefs(
            features=StreamDef(field='image', transforms=transforms),
            # first column in map file is referred to as 'image'
            labels=StreamDef(field='label', shape=_NUM_CLASSES))),  # and second as 'label'
        randomize=train,
        max_samples=total_number_of_samples,
        multithreaded_deserializer=True)


def create_network(num_convolution_layers):
    """ Create network

    """
    # Input variables denoting the features and label data
    input_var = cntk.input_variable((_NUM_CHANNELS, _IMAGE_HEIGHT, _IMAGE_WIDTH))
    label_var = cntk.input_variable((_NUM_CLASSES))

    # create model, and configure learning parameters
    # Instantiate the feedforward classification model
    input_removemean = minus(input_var, constant(128))
    scaled_input = element_times(constant(0.00390625), input_removemean)

    print('Creating NN model')
    with layers.default_options(activation=relu, pad=True):
        model = layers.Sequential([
            layers.For(range(num_convolution_layers), lambda: [
                layers.Convolution2D((3, 3), 64),
                layers.Convolution2D((3, 3), 64),
                layers.MaxPooling((3, 3), (2, 2))
            ]),
            layers.For(range(2), lambda i: [
                layers.Dense([256, 128][i]),
                layers.Dropout(0.5)
            ]),
            layers.Dense(_NUM_CLASSES, activation=None)
        ])(scaled_input)

    # loss and metric
    ce = cross_entropy_with_softmax(model, label_var)
    pe = classification_error(model, label_var)

    return {
        'name': 'convnet',
        'feature': input_var,
        'label': label_var,
        'ce': ce,
        'pe': pe,
        'output': model
    }


def train_and_test(network, trainer, train_source, test_source, minibatch_size, epoch_size, restore,
                   model_path=_MODEL_PATH, cv_config=None):
    """ Train and test

    """
    # define mapping from intput streams to network inputs
    input_map = {
        network['feature']: train_source.streams.features,
        network['label']: train_source.streams.labels
    }

    cntk.training_session(
        trainer=trainer,
        mb_source=train_source,
        mb_size=minibatch_size,
        model_inputs_to_streams=input_map,
        checkpoint_config=cntk.CheckpointConfig(filename=os.path.join(model_path, _MODEL_NAME), restore=restore),
        progress_frequency=epoch_size,
        cv_config=cv_config
    ).train()


def create_trainer(network, minibatch_size, epoch_size, progress_printer):
    """ Create trainer 
    """

    # Set learning parameters
    lr_per_sample = [0.0015625] * 10 + [0.00046875] * 10 + [0.00015625]
    momentum_time_constant = [0] * 20 + [-minibatch_size / np.log(0.9)]
    l2_reg_weight = 0.002

    lr_schedule = learning_rate_schedule(lr_per_sample, epoch_size=epoch_size, unit=UnitType.sample)
    mm_schedule = momentum_as_time_constant_schedule(momentum_time_constant)

    learner = momentum_sgd(network['output'].parameters,
                           lr_schedule,
                           mm_schedule,
                           l2_regularization_weight=l2_reg_weight)

    return Trainer(network['output'], (network['ce'], network['pe']), learner, progress_printer)


def create_results_callback(filename, **kwargs):
    def simple_callback(index, average_error, cv_num_samples, cv_num_minibatches):
        _save_results(average_error, filename, **kwargs)
        return False
    return simple_callback


def convnet_cifar10(train_source,
                    test_source,
                    epoch_size,
                    num_convolution_layers=2,
                    minibatch_size=64,
                    max_epochs=30,
                    log_file=None,
                    tboard_log_dir='.',
                    results_path=_MODEL_PATH):
    _cntk_py.set_computation_network_trace_level(0)

    logger.info("""Running network with: 
                {num_convolution_layers} convolution layers
                {minibatch_size}  minibatch size
                for {max_epochs} epochs""".format(
                    num_convolution_layers=num_convolution_layers,
                    minibatch_size=minibatch_size,
                    max_epochs=max_epochs
                ))

    network = create_network(num_convolution_layers)

    progress_printer = ProgressPrinter(
        tag='Training',
        log_to_file=log_file,
        rank=cntk.Communicator.rank(),
        num_epochs=max_epochs)
    tensorboard_writer = TensorBoardProgressWriter(freq=10,
                                                   log_dir=tboard_log_dir,
                                                   model=network['output'])
    trainer = create_trainer(network, minibatch_size, epoch_size, [progress_printer, tensorboard_writer])

    cv_config = CrossValidationConfig(minibatch_source=test_source,
                                      minibatch_size=16,
                                      callback=create_results_callback(os.path.join(results_path, "model_results.json"),
                                                                       num_convolution_layers=num_convolution_layers,
                                                                       minibatch_size=minibatch_size,
                                                                       max_epochs=max_epochs))
    train_and_test(network,
                   trainer,
                   train_source,
                   test_source,
                   minibatch_size,
                   epoch_size,
                   restore=False,
                   cv_config=cv_config)
    network['output'].save(os.path.join(results_path, _MODEL_NAME))


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--datadir',
                        help='Data directory where the CIFAR dataset is located',
                        required=True)
    parser.add_argument('-m', '--modeldir',
                        help='directory for saving model',
                        required=False,
                        default=_MODEL_PATH)
    parser.add_argument('-logfile', '--logfile', help='Log file', required=False, default=None)
    parser.add_argument('-tensorboard_logdir', '--tensorboard_logdir',
                        help='Directory where TensorBoard logs should be created',
                        required=False,
                        default='.')
    parser.add_argument('-e', '--max_epochs',
                        help='Total number of epochs to train',
                        type=int,
                        required=False,
                        default='20')
    parser.add_argument('--num_convolution_layers',
                        help='Number of convolution layers',
                        type=int,
                        required=False,
                        default='2')
    parser.add_argument('--minibatch_size',
                        help='Number of examples in each minibatch',
                        type=int,
                        required=False,
                        default='64')

    args = vars(parser.parse_args())
    epochs = int(args['max_epochs'])
    model_path = args['modeldir']

    data_path = args['datadir']
    if not os.path.exists(data_path):
        raise RuntimeError("Folder %s does not exist" % data_path)

    train_source = create_image_mb_source(os.path.join(data_path, 'train_map.txt'),
                                          os.path.join(data_path, 'CIFAR-10_mean.xml'),
                                          train=True,
                                          total_number_of_samples=epochs * _EPOCH_SIZE)

    test_source = create_image_mb_source(os.path.join(data_path, 'test_map.txt'),
                                         os.path.join(data_path, 'CIFAR-10_mean.xml'),
                                         train=False,
                                         total_number_of_samples=cntk.io.FULL_DATA_SWEEP)


    unique_path = os.path.join(model_path, _get_unique_id())
    convnet_cifar10(train_source,
                    test_source,
                    _EPOCH_SIZE,
                    num_convolution_layers=args['num_convolution_layers'],
                    minibatch_size=args['minibatch_size'],
                    max_epochs=args['max_epochs'],
                    log_file=None,
                    tboard_log_dir='.',
                    results_path=unique_path)


