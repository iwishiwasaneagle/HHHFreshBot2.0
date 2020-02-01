# -*- coding: utf-8 -*-
import spotipy.util as util
import spotipy
import sqlite3
import time
import requests
import json
import base64
import logger
from vals import SPOTIPI_CLIENT_SECRET, SPOTIPI_CLIENT_ID, SPOTIPI_REDIRECT_URL

log = logger.get_logger(__name__)


def weekly_playlist(sqlite3_cursor):
    log.debug("Beginning weekly_playlist...")
    t = time.time()
    c = sqlite3_cursor
    c.execute("SELECT title FROM posts WHERE TIME>{} OR SCORE<{}".format(
                    time.time() - 7*24*60*60,
                    50
                ))
    weekly_songs = ["".join(f[0].split("] ")[1:]) for f in c.fetchall()]
    log.info("There are {} songs this week!".format(len(weekly_songs)))



    # Change this if you're wanting to use it and aren't me
    username = 'iwishiwasaneagle'
    scope = 'playlist-modify-public ugc-image-upload'

    token = util.prompt_for_user_token(
        username,
        scope,
        client_id=SPOTIPI_CLIENT_ID,
        client_secret=SPOTIPI_CLIENT_SECRET,
        redirect_uri=SPOTIPI_REDIRECT_URL)
    log.debug("Spotify auth token received")

    sp = spotipy.Spotify(auth=token)

    playlists = sp.user_playlists(username)
    weekly_playlist = None
    name = "Weekly r/HHHFreshness"
    while playlists:
        for i, playlist in enumerate(playlists['items']):
            if name == playlist['name']:
                weekly_playlist = playlist
                log.debug("Found playlist with name {}".format(name))
                break
        if playlists['next']:
            playlists = sp.next(playlists)
        else:
            playlists = None

    if weekly_playlist == None:
        log.info("Creating playlist with name {}".format(name))
        weekly_playlist = sp.user_playlist_create(username, name)

        # Update playlist's description
        url = "https://api.spotify.com/v1/playlists/{playlist_id}".format(
            playlist_id = weekly_playlist['id']
        )
        headers = {
            "Authorization":"Bearer {token}".format(token=token),
            "Accept": "application/json",
            "Content-Type": "application/json"}
        data = {"description":"The weekly [FRESH]ness from hiphopheads. Created by iwishiwasaneagle"}
        requests.put(url, headers=headers, data=json.dumps(data))

        # Update playlist's cover photo
        url = "https://api.spotify.com/v1/playlists/{playlist_id}/images".format(
            playlist_id = weekly_playlist['id']
        )
        headers = {
            "Authorization":"Bearer {token}".format(token=token),
            "Accept": "image/jpeg",
            "Content-Type": "image/jpeg"}
        with open('image.jpeg', 'rb') as image:
            image = base64.b64encode(image.read())
            print(requests.put(url, headers=headers, data=image))

    songs_in_playlist = sp.user_playlist_tracks(username, weekly_playlist['id'])
    songs_in_playlist = [f['track']['uri'] for f in songs_in_playlist['items']]

    songs_to_add = []
    for song in weekly_songs:
        try:
            search = sp.search(song)
            for i, result in enumerate(search["tracks"]['items']):
                songs_to_add.append(result["uri"])
                break
        except Exception as e:
            log.error("Eror whilst searching for song with name '{}'".format(song))
            log.error(e)
    log.info("{}/{} ({}%) of fresh songs have been found on spotify".format(
        len(songs_to_add), len(weekly_songs), round((100*len(songs_to_add))/len(weekly_songs),1)
    ))

    songs_to_remove = [f for f in songs_in_playlist]
    sp.user_playlist_remove_all_occurrences_of_tracks(
        username,
        weekly_playlist['id'],
        songs_to_remove)

    sp.user_playlist_add_tracks(
        username,
        weekly_playlist['id'],
        songs_to_add
    )

    log.debug("weekly_playlist was succesfully run in {}s".format(time.time()-t))
    try:
        return_Val = weekly_playlist['external_urls']['spotify'], len(songs_to_add), len(weekly_songs), round((100*len(songs_to_add))/len(weekly_songs),1)
    except:
        return_Val = "https://open.spotify.com/playlist/2f4DSt4MUFppJvGdySWCIT?si=SHFA15VvSoGWYWHlrsWWwQ", len(songs_to_add), len(weekly_songs), round((100*len(songs_to_add))/len(weekly_songs),1)

    return return_Val

if __name__ == "__main__":
    log.debug("Running weekly_playlist test")
    conn = sqlite3.connect("fresh.db")
    c = conn.cursor()
    weekly_playlist(c)
