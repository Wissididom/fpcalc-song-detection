#!/usr/bin/python3

# correlation.py
import subprocess
import traceback

import numpy
import os

# seconds to sample audio file for
sample_time = 500
# number of points to scan cross correlation over
span = 150
# step size (in points) of cross correlation
step = 1
# minimum number of points that must overlap in cross correlation
# exception is raised if this cannot be met
min_overlap = 20

fpcalc_cache = {}

def get_audio_duration(filename):
    out = subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', filename])
    return int(float(out))

def extract_audio_chunk_bytes(filename, offset, duration):
    """
    Extract a chunk of audio as WAV bytes from 'filename' starting at 'offset' seconds
    for 'duration' seconds.
    """
    cmd = ['ffmpeg', '-ss', str(offset), '-t', str(duration), '-i', filename, '-f', 'wav', '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '2', '-hide_banner', '-loglevel', 'error', '-']
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {err.decode()}")
    return out

def calculate_fingerprint(filename, offset=0, duration=sample_time):
    """
    Calculate the fingerprint of a chunk in 'filename' starting at 'offset' with 'duration' seconds,
    using fpcalc reading WAV data from stdin.
    """
    print("Calculating fingerprint by fpcalc for %s at offset %d" % (filename, offset))
    audio_chunk_bytes = extract_audio_chunk_bytes(filename, offset, duration)
    proc = subprocess.Popen(['fpcalc', '-raw', '-ts', '-'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=False)
    stdout, stderr = proc.communicate(input=audio_chunk_bytes)
    if proc.returncode != 0:
        raise RuntimeError(f"fpcalc failed: {stderr.decode()}")
    fpcalc_out = stdout.decode()
    fingerprint_index = fpcalc_out.find('FINGERPRINT=')
    if fingerprint_index == -1:
        raise ValueError("Fingerprint not found in fpcalc output")
    fingerprint_str = fpcalc_out[fingerprint_index + len('FINGERPRINT='):].strip()
    # convert fingerprint to list of integers
    fingerprints = list(map(int, fingerprint_str.split(',')))
    return fingerprints

def get_fingerprints(dirname):
    result = []
    for root, dirs, files in os.walk(dirname):
        for file in files:
            result.append(root + os.sep + file)
    return result

def get_fingerprint(filename):
    fpcalc_content = fpcalc_cache.get(filename)
    if fpcalc_content is None:
        f = open(filename, "r")
        fpcalc_content = ''.join(f.readlines())
        f.close()
        fpcalc_cache.update({filename: fpcalc_content})
    fingerprint_index = fpcalc_content.find('FINGERPRINT=') + 12
    # convert fingerprint to list of integers
    fingerprints = list(map(int, fpcalc_content[fingerprint_index:].split(',')))
    return fingerprints
  
# returns correlation between lists
def correlation(listx, listy):
    if len(listx) == 0 or len(listy) == 0:
        # Error checking in main program should prevent us from ever being
        # able to get here.
        raise Exception('Empty lists cannot be correlated.')
    if len(listx) > len(listy):
        listx = listx[:len(listy)]
    elif len(listx) < len(listy):
        listy = listy[:len(listx)]
    
    covariance = 0
    for i in range(len(listx)):
        covariance += 32 - bin(listx[i] ^ listy[i]).count("1")
    covariance = covariance / float(len(listx))
    
    return covariance / 32
  
# return cross correlation, with listy offset from listx
def cross_correlation(listx, listy, offset):
    if offset > 0:
        listx = listx[offset:]
        listy = listy[:len(listx)]
    elif offset < 0:
        offset = -offset
        listy = listy[offset:]
        listx = listx[:len(listy)]
    if min(len(listx), len(listy)) < min_overlap:
        # Error checking in main program should prevent us from ever being
        # able to get here.
        return None
    #raise Exception('Overlap too small: %i' % min(len(listx), len(listy)))
    return correlation(listx, listy)
  
# cross correlate listx and listy with offsets from -span to span
def compare(listx, listy, span, step):
    if span > min(len(listx), len(listy)):
        # Error checking in main program should prevent us from ever being
        # able to get here.
        raise Exception('span >= sample size: %i >= %i\n'
                        % (span, min(len(listx), len(listy)))
                        + 'Reduce span, reduce crop or increase sample_time.')
    corr_xy = []
    for offset in numpy.arange(-span, span + 1, step):
        corr_xy.append(cross_correlation(listx, listy, offset))
    return corr_xy

# return index of maximum value in list
def max_index(listx):
    max_index = 0
    max_value = listx[0]
    for i, value in enumerate(listx):
        if value > max_value:
            max_value = value
            max_index = i
    return max_index
  
def get_max_corr(corr, threshold=0.5):
    max_corr_index = max_index(corr)
    max_corr_offset = -span + max_corr_index * step
    return max_corr_index, max_corr_offset

def is_match(corr_scores, threshold=0.75, min_consistent_offsets=3, max_offset_deviation=5):
    """
    Determine if a match exists given correlation scores over multiple offsets.

    Args:
        corr_scores (list of tuples): List of (correlation_value, offset) pairs, e.g.
            [(0.80, -2), (0.78, -3), (0.82, -1), (0.45, 10)]
        threshold (float): Minimum correlation value to consider a 'high' correlation.
        min_consistent_offsets (int): Minimum number of high correlations with consistent offsets needed.
        max_offset_deviation (int): Maximum allowed difference between offsets to be considered consistent.

    Returns:
        bool: True if match conditions met, False otherwise.
    """
    high_corrs = [(c, o) for c, o in corr_scores if c >= threshold]
    if len(high_corrs) < min_consistent_offsets:
        # Not enough high correlation points to call a match
        return False
    high_corrs.sort(key=lambda x: x[1])
    offsets = [o for _, o in high_corrs]
    for i in range(len(offsets)):
        cluster = [offsets[i]]
        for j in range(i + 1, len(offsets)):
            if offsets[j] - cluster[0] <= max_offset_deviation:
                cluster.append(offsets[j])
            else:
                break
        if len(cluster) >= min_consistent_offsets:
            return True
    return False

def correlate(source_file, fingerprints_dir):
    fingerprints = get_fingerprints(fingerprints_dir)
    duration = get_audio_duration(source_file) # In seconds
    window = sample_time
    step = 10
    found_songs = []
    for offset in range(0, duration - window + 1, step):
        #if offset >= 960: # 16 minutes
        #    break
        print(f"Fingerprinting {source_file} at offset {offset}s")
        try:
            source_fingerprint = calculate_fingerprint(source_file, offset, duration=window)
        except Exception as e:
            print(f"Failed to calculate fingerprint at offset {offset}: {e}")
            print(traceback.format_exc())
            continue
        for short_clip_fp_path in fingerprints:
            short_fingerprint = get_fingerprint(short_clip_fp_path)
            if len(short_fingerprint) == 0 or len(source_fingerprint) == 0:
                continue
            span_to_use = min(span, min(len(source_fingerprint), len(short_fingerprint)) - 1)
            if span_to_use < min_overlap:
                continue
            corr = compare(source_fingerprint, short_fingerprint, span_to_use, step)
            offsets = list(numpy.arange(-span_to_use, span_to_use + 1, step))
            corr_scores = list(zip(corr, offsets))
            if is_match(corr_scores, threshold=0.60, min_consistent_offsets=1, max_offset_deviation=5):
                max_corr_index, max_corr_offset = get_max_corr(corr)
                print(f"Match found between {source_file} (offset {offset}s) and {short_clip_fp_path}")
                print(f"Correlation: {corr[max_corr_index] * 100.0:.2f}% at offset {max_corr_offset}")
                found_songs.append((short_clip_fp_path.replace(f"{fingerprints_dir}/", '').replace('.fpcalc', ''), corr[max_corr_index] * 100.0, offset))
            else:
                print(f"No match for {short_clip_fp_path} at offset {offset}s")
    return found_songs
