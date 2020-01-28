# -*- coding: utf-8 -*-
"""
Fundamental Frequency:
this file:
- recieves the EEG stream from muselsl
- performs several transformations (Fast Fourier Transforms)
to extract the alpha, beta, delta and theta waves
- computes the ratio beta/alpha
- send the value and the sigmoid of the value as OSC to the specified address

Adapted from https://github.com/alexandrebarachant/muse-lsl/blob/master/examples/neurofeedback.py
"""

import numpy as np  # Module that simplifies computations on matrices
from pylsl import StreamInlet, resolve_byprop  # Module to receive EEG data
import utils  # Utility functions
from pythonosc import udp_client  # Module for OSC

# Handy little enum to make code more readable


class Band:
    Delta = 0
    Theta = 1
    Alpha = 2
    Beta = 3


""" EXPERIMENTAL PARAMETERS """
# Modify these to change aspects of the signal processing

# Length of the EEG data buffer (in seconds)
# This buffer will hold last n seconds of data and be used for calculations
BUFFER_LENGTH = 10

# Length of the epochs used to compute the FFT (in seconds)
EPOCH_LENGTH = 1

# Amount of overlap between two consecutive epochs (in seconds)
OVERLAP_LENGTH = 1 - 1 / 60

# Amount to 'shift' the start of each next consecutive epoch
SHIFT_LENGTH = EPOCH_LENGTH - OVERLAP_LENGTH

# Index of the channel(s) (electrodes) to be used
# 0 = left ear, 1 = left forehead, 2 = right forehead, 3 = right ear
INDEX_CHANNEL = [0, 1, 2, 3]


def get_band_powers(inlet, eeg_buffer, filter_state, band_buffer):
    """ 3.1 ACQUIRE DATA """
    # Obtain EEG data from the LSL stream
    eeg_data, timestamp = inlet.pull_chunk(
        timeout=1, max_samples=int(SHIFT_LENGTH * fs))

    # Only keep the channel we're interested in
    ch_data = np.array(eeg_data)[:, INDEX_CHANNEL]
    # Update EEG buffer with the new data
    eeg_buffer, filter_state = utils.update_buffer(
        eeg_buffer, ch_data, notch=True,
        filter_state=filter_state)

    """ 3.2 COMPUTE BAND POWERS """
    # Get newest samples from the buffer
    data_epoch = utils.get_last_data(eeg_buffer,
                                     EPOCH_LENGTH * fs)

    # Compute band powers
    band_powers = utils.compute_band_powers(data_epoch, fs)
    band_buffer, _ = utils.update_buffer(band_buffer,
                                         np.asarray([band_powers]))
    # Compute the average band powers for all epochs in buffer
    # This helps to smooth out noise
    smooth_band_powers = np.mean(band_buffer, axis=0)

    return smooth_band_powers


if __name__ == "__main__":

    """ 0. CREATE THE OSC SENDER """
    # Modify address and port accordingly
    sender = udp_client.SimpleUDPClient('127.0.0.1', 4559)

    def send_osc_message(value, name):
        sender.send_message('/fund_freq/' + name, value)

    """ 1. CONNECT TO EEG STREAM """

    # Search for active LSL streams
    print('Looking for an EEG stream...')
    streams = resolve_byprop('type', 'EEG', timeout=2)
    if len(streams) == 0:
        raise RuntimeError('Can\'t find EEG stream.')

    # Set active EEG stream to inlet and apply time correction
    print("Start acquiring data")
    inlet = StreamInlet(streams[0], max_chunklen=12)
    eeg_time_correction = inlet.time_correction()

    # Get the stream info and description
    info = inlet.info()
    description = info.desc()

    # Get the sampling frequency
    # This is an important value that represents how many EEG data points are
    # collected in a second. This influences our frequency band calculation.
    # for the Muse 2016, this should always be 256
    fs = int(info.nominal_srate())

    """ 2. INITIALIZE BUFFERS """

    # Initialize raw EEG data buffer
    eeg_buffer = np.zeros((int(fs * BUFFER_LENGTH), 4))
    filter_state = None  # for use with the notch filter

    # Compute the number of epochs in "buffer_length"
    n_win_test = int(np.floor((BUFFER_LENGTH - EPOCH_LENGTH) /
                              SHIFT_LENGTH + 1))

    # Initialize the band power buffer (for plotting)
    # bands will be ordered: [delta, theta, alpha, beta]
    band_buffer = np.zeros((n_win_test, 4))

    """ 3. GET DATA """

    # The try/except structure allows to quit the while loop by aborting the
    # script with <Ctrl-C>
    print('Press Ctrl-C in the console to break the while loop.')

    try:
        # The following loop acquires data, computes band powers,
        # and sends OSC neurofeedback metric based on those band powers
        while True:

            # """ 3.1 ACQUIRE DATA """
            # # Obtain EEG data from the LSL stream
            # eeg_data, timestamp = inlet.pull_chunk(
            #     timeout=1, max_samples=int(SHIFT_LENGTH * fs))

            # # Only keep the channel we're interested in
            # ch_data = np.array(eeg_data)[:, INDEX_CHANNEL]
            # # Update EEG buffer with the new data
            # eeg_buffer, filter_state = utils.update_buffer(
            #     eeg_buffer, ch_data, notch=True,
            #     filter_state=filter_state)

            # """ 3.2 COMPUTE BAND POWERS """
            # # Get newest samples from the buffer
            # data_epoch = utils.get_last_data(eeg_buffer,
            #                                  EPOCH_LENGTH * fs)

            # # Compute band powers
            # band_powers = utils.compute_band_powers(data_epoch, fs)
            # band_buffer, _ = utils.update_buffer(band_buffer,
            #                                      np.asarray([band_powers]))
            # # Compute the average band powers for all epochs in buffer
            # # This helps to smooth out noise
            # smooth_band_powers = np.mean(band_buffer, axis=0)

            smooth_band_powers = get_band_powers(
                inlet, eeg_buffer, filter_state, band_buffer)

            # print('Delta: ', band_powers[Band.Delta], ' Theta: ', band_powers[Band.Theta],
            #       ' Alpha: ', band_powers[Band.Alpha], ' Beta: ', band_powers[Band.Beta])

            """ 3.3 COMPUTE NEUROFEEDBACK METRICS """
            # Extract the Alpha and Beta waves
            alpha = smooth_band_powers[Band.Alpha]
            beta = smooth_band_powers[Band.Beta]
            # Computes the ratio and its sigmoid
            score = beta / alpha
            sig_score = utils.sigmoid(score)
            # Sends the OSC values (they need to be str for Unity)
            send_osc_message(str(score), "score")
            send_osc_message(str(sig_score), "sig_score")

    except KeyboardInterrupt:
        print('Closing!')
