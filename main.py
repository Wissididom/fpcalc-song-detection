#!/usr/bin/python3
# main.py
import argparse
import datetime

from correlation import correlate

def initialize():
    parser = argparse.ArgumentParser()
    parser.add_argument("-sf", "--search-file", help="file to search through for songs")
    parser.add_argument("-fp", "--fingerprints", default="fingerprints", help="fingerprints directory")
    args = parser.parse_args()
    return (args.search_file or "input.mp4"), args.fingerprints

def get_days_hours_minutes_seconds_from_timedelta(td):
    return td.days, td.seconds // 3600, (td.seconds // 60) % 60, td.seconds % 60

def make_songlist(found_songs):
    songlist = ""
    last_song = None
    for found_song in found_songs:
        song_name, correlation, offset = found_song
        song_name = song_name.replace('.mp3', '')
        if last_song == song_name:
            last_song = song_name
            continue
        delta = datetime.timedelta(seconds=offset)
        days, hours, minutes, seconds = get_days_hours_minutes_seconds_from_timedelta(delta)
        time = str(seconds).zfill(2)
        if minutes > 0:
            time = f"{str(minutes).zfill(2)}:" + time
        if hours > 0:
            time = f"{str(hours).zfill(2)}:" + time
        if days > 0:
            time = f"{str(days).zfill(2)}:" + time
        if songlist == "":
            songlist = f"{time} - {song_name}"
        else:
            songlist += f"\n{time} - {song_name}"
        last_song = song_name
    return songlist

if __name__ == "__main__":
    search_file, fingerprints = initialize()
    found_songs = correlate(search_file, fingerprints)
    print(make_songlist(found_songs))
