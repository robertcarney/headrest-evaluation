import glob
import matplotlib.pyplot as plt
import mne
import numpy as np
import matplotlib

# Use Agg backend to prevent display of figures
matplotlib.use('Agg')

# Specify SSVEP data directory
# E.g. './data/carson/ssvep/*.gdf'
dir = './data/brian/ssvep/*.gdf'

# Find and list SSVEP data files
SSVEPfiles = glob.glob(dir)

name = (dir.split('/')[2]).title()
# Define EEG channels of interest
eeg_channels = [
    'FP1', 'FPZ', 'FP2', 'F7', 'F3', 'FZ', 'F4', 'F8', 
    'FC5', 'FC1', 'FC2', 'FC6', 'T7', 'C3', 'CZ', 'C4', 
    'T8', 'CP5', 'CP1', 'CP2', 'CP6', 'P7', 'P3', 'PZ', 
    'P4', 'P8', 'POZ', 'O1', 'OZ', 'O2'
]
eog_channels = ['sens13', 'sens14', 'sens15']
standard_montage = mne.channels.make_standard_montage('standard_1020')

def snr_spectrum(psd, noise_n_neighbor_freqs=1, noise_skip_neighbor_freqs=1):
    """Compute SNR spectrum from PSD spectrum using convolution.

    Parameters
    ----------
    psd : ndarray, shape ([n_trials, n_channels,] n_frequency_bins)
        Data object containing PSD values. Works with arrays as produced by
        MNE's PSD functions or channel/trial subsets.
    noise_n_neighbor_freqs : int
        Number of neighboring frequencies used to compute noise level.
        increment by one to add one frequency bin ON BOTH SIDES
    noise_skip_neighbor_freqs : int
        set this >=1 if you want to exclude the immediately neighboring
        frequency bins in noise level calculation

    Returns
    -------
    snr : ndarray, shape ([n_trials, n_channels,] n_frequency_bins)
        Array containing SNR for all epochs, channels, frequency bins.
        NaN for frequencies on the edges, that do not have enough neighbors on
        one side to calculate SNR.
    """
    # Construct a kernel that calculates the mean of the neighboring
    # frequencies
    averaging_kernel = np.concatenate(
        (
            np.ones(noise_n_neighbor_freqs),
            np.zeros(2 * noise_skip_neighbor_freqs + 1),
            np.ones(noise_n_neighbor_freqs),
        )
    )
    averaging_kernel /= averaging_kernel.sum()

    # Calculate the mean of the neighboring frequencies by convolving with the
    # averaging kernel.
    mean_noise = np.apply_along_axis(
        lambda psd_: np.convolve(psd_, averaging_kernel, mode="valid"), axis=-1, arr=psd
    )

    # The mean is not defined on the edges so we will pad it with nas. The
    # padding needs to be done for the last dimension only so we set it to
    # (0, 0) for the other ones.
    edge_width = noise_n_neighbor_freqs + noise_skip_neighbor_freqs
    pad_width = [(0, 0)] * (mean_noise.ndim - 1) + [(edge_width, edge_width)]
    mean_noise = np.pad(mean_noise, pad_width=pad_width, constant_values=np.nan)

    return psd / mean_noise

# Define mapping of event IDs to frequencies
freq_mapping = {
    2: 7.5,
    3: 8.57,
    4: 10,
    5: 12
}

sfreq = 512

# Create a report for the current file
report = mne.Report(title='SSVEP Test Report', verbose=True)

for i, file in enumerate(SSVEPfiles):
    # Read the raw data
    raw = mne.io.read_raw_gdf(file, eog=eog_channels, preload=True, stim_channel='Status')
    # Set montage for naming
    raw.set_montage(standard_montage, match_case=False)
    # Pick only the EEG channels of interest
    raw.pick_channels(eeg_channels)

    # Apply notch filter of 60 Hz
    raw.notch_filter(60, verbose='INFO')

    events, _ = mne.events_from_annotations(raw)

    for event_id, freq in freq_mapping.items():
        # Extract epochs for the current frequency
        epoch = mne.Epochs(raw, events, event_id, event_repeated='merge', tmin=1, tmax=8, baseline=None, verbose='INFO')

        spectrum = epoch[f'{event_id}'][0].compute_psd(method='welch', fmin=1, fmax=40)
        figure = spectrum.plot()

        psd, freqs = spectrum.get_data(return_freqs=True)

        figure.axes[0].set_title(f'SSVEP ({freq} Hz)')
        figure.axes[0].axvline(x=freq, color='red', linestyle='--', label='1f')
        figure.axes[0].axvline(x=freq*2, color='blue', linestyle='--', label='2f')
        figure.axes[0].axvline(x=freq*3, color='green', linestyle='--', label='3f')
        figure.legend(loc='lower left')

        # Add the figure to the report
        report.add_figure(figure, f'SSVEP ({freq} Hz)', section=f'SSVEP Trial {i+1}')
        plt.close()
        # Average PSD across epochs (only have one)
        psd_mean = psd.mean(axis=0)

        # Compute SNR
        snr = snr_spectrum(psd_mean, noise_n_neighbor_freqs=3, noise_skip_neighbor_freqs=1)

        # Average across epochs (only have one)
        snr_mean = snr.mean(axis=0)
        snr_std = snr.std(axis=0)

        # Plot SNR spectrum with mean and standard deviation
        figure_snr = plt.figure()
        plt.plot(freqs, snr_mean, zorder=2, color='black')  # Plotting the mean SNR
        plt.fill_between(freqs, snr_mean - snr_std, snr_mean + snr_std, color='black', alpha=0.2, zorder=1)  # Filling between ±1 SD

        plt.title(f'SNR ({freq} Hz)')
        plt.xlabel('Frequency (Hz)')
        plt.ylabel('SNR')

        # Marking stimulus frequency and its harmonics
        plt.axvline(x=freq, color='red', linestyle=':', dashes=[1, 5], label='1f', zorder=0)
        plt.axvline(x=freq*2, color='blue', linestyle=':', dashes=[1, 5], label='2f', zorder=0)
        plt.axvline(x=freq*3, color='green', linestyle=':', dashes=[1, 5], label='3f', zorder=0)

        plt.legend()
        # Add the figure to the report
        report.add_figure(figure_snr, f'SNR ({freq} Hz)', section=f'SSVEP Trial {i+1}')
        plt.close()
report.save(f'./reports/Brian.html', overwrite=True)