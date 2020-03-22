# -*- coding: utf-8 -*-
import re
import json
import operator
import binascii
import base64
import execjs
from ssl import SSLError
from threading import Thread, Event, RLock, Semaphore
import calendar
import time
from random import randint
import uuid

import requests
from ws4py.client.threadedclient import WebSocketClient

from proto import mercury_pb2, metadata_pb2, playlist4changes_pb2,\
    playlist4ops_pb2, playlist4service_pb2, toplist_pb2, bartender_pb2, \
    radio_pb2

#### from .proto import playlist4meta_pb2, playlist4issues_pb2, playlist4content_pb2


base62 = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

WORK_RUNNER = """
var main = {
  args: null,

  reply: function() {
    main.args = Array.prototype.slice.call(arguments);
  },

  run: function() {
    %s

    return main.args;
  }
};
"""

IMAGE_HOST = "d3rt1990lpmkn.cloudfront.net"


class Logging():
    log_level = 1

    hooks = {}

    @classmethod
    def hook(cls, level, handler):
        cls.hooks[level] = handler

    @classmethod
    def write(cls, level, str):
        if level in cls.hooks:
            cls.hooks[level](str)
            return True

        if cls.log_level < level:
            return True

        return False

    @classmethod
    def debug(cls, str):
        if cls.write(3, str):
            return

        print "[DEBUG] " + str

    @classmethod
    def notice(cls, str):
        if cls.write(2, str):
            return

        print "[NOTICE] " + str

    @classmethod
    def warn(cls, str):
        if cls.write(1, str):
            return

        print "[WARN] " + str

    @classmethod
    def error(cls, str):
        if cls.write(0, str):
            return

        print "[ERROR] " + str


class WrapAsync():
    timeout = 30

    def __init__(self, timeout, callback, func, *args):
        self.marker = Event()

        if timeout is not None:
            self.timeout = timeout

        if callback is None:
            callback = self.callback
        elif type(callback) == list:
            callback = callback+[self.callback]
        else:
            callback = [callback, self.callback]

        self.data = False
        self.could_send = func(*args, callback=callback)

    def callback(self, *args):
        self.data = args
        self.marker.set()

    def get_data(self):
        try:
            if not self.could_send:
                return False

            self.marker.wait(timeout=self.timeout)

            if len(self.data) > 0 and type(self.data[0] == SpotifyAPI):
                self.data = self.data[1:]

            return self.data if len(self.data) > 1 else self.data[0]
        except:
            return False


class SpotifyClient(WebSocketClient):
    def set_api(self, api):
        self.api_object = api

    def opened(self):
        self.api_object.login()

    def received_message(self, m):
        self.api_object.recv_packet(m)

    def closed(self, code, message):
        self.api_object.shutdown()


class SpotifyUtil():
    @staticmethod
    def gid2id(gid):
        return binascii.hexlify(gid).rjust(32, "0")

    @staticmethod
    def id2uri(uritype, v):
        if not v:
            return None

        res = []
        v = int(v, 16)
        while v > 0:
            res = [v % 62] + res
            v /= 62
        id = ''.join([base62[i] for i in res])
        return ("spotify:"+uritype+":"+id.rjust(22, "0"))

    @staticmethod
    def uri2id(uri):
        parts = uri.split(":")
        if len(parts) > 3 and parts[3] == "playlist":
            s = parts[4]
        else:
            s = parts[2]

        v = 0
        for c in s:
            v = v * 62 + base62.index(c)
        return hex(v)[2:-1].rjust(32, "0")

    @staticmethod
    def gid2uri(uritype, gid):
        id = SpotifyUtil.gid2id(gid)
        uri = SpotifyUtil.id2uri(uritype, id)
        return uri

    @staticmethod
    def get_uri_type(uri):
        uri_parts = uri.split(":")

        if len(uri_parts) >= 3 and uri_parts[1] == "local":
            return "local"
        elif len(uri_parts) >= 5:
            return uri_parts[3]
        elif len(uri_parts) >= 4 and uri_parts[3] == "starred":
            return "playlist"
        elif len(uri_parts) >= 3:
            return uri_parts[1]
        else:
            return False

    @staticmethod
    def is_local(uri):
        return SpotifyUtil.get_uri_type(uri) == "local"

    @staticmethod
    def is_track_uri_valid(track_uri):
        try:
            return track_uri != None and len(track_uri) == 36 and track_uri[0:14] == "spotify:track:"
        except:
            return False

class SpotifyAPI():
    def __init__(self, login_callback_func=False, log_level=1):
        Logging.log_level = log_level

        self.auth_server       = "play.spotify.com"
        self.login_callback    = login_callback_func
        self.disconnecting     = False
        self.connecting        = False
        self.stop_heartbeat    = False
        self.ws                = None
        self.ws_lock           = RLock()
        self.reconnect_marker  = Semaphore(1)
        self.connecting_marker = Semaphore(1)
        self.shutdown_marker   = Semaphore(1)
        self.disconnect_marker = Semaphore(1)
        self.start()

    def start(self):
        self.logged_in_marker = Event()
        self.heartbeat_marker = Event()
        self.username = None
        self.password = None
        self.account_type = None
        self.country = None
        self.settings = None
        self.seq = 0
        self.cmd_callbacks = {}
        self.is_logged_in = False

    def auth(self, username, password):
        if self.settings is not None:
            Logging.warn("You must only authenticate once per API object")
            return False

        headers = {
            "Origin": "https://play.spotify.com",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/31.0.1650.63 Safari/537.36"
        }

        session = requests.session()
        resp = session.get("https://" + self.auth_server, headers=headers)
        data = resp.text

        #csrftoken
        rx = re.compile("\"csrftoken\":\"(.*?)\"")
        r = rx.search(data)

        if not r or len(r.groups()) < 1:
            Logging.error("There was a problem authenticating, no auth secret found")
            self.do_login_callback(False)
            return False
        secret = r.groups()[0]

        #trackingID
        rx = re.compile("\"trackingId\":\"(.*?)\"")
        r = rx.search(data)

        if not r or len(r.groups()) < 1:
            Logging.error("There was a problem authenticating, no auth trackingId found")
            self.do_login_callback(False)
            return False
        trackingId = r.groups()[0]

        #referrer
        rx = re.compile("\"referrer\":\"(.*?)\"")
        r = rx.search(data)

        if not r or len(r.groups()) < 1:
            Logging.error("There was a problem authenticating, no auth referrer found")
            self.do_login_callback(False)
            return False
        referrer = r.groups()[0]

        #landingURL
        rx = re.compile("\"landingURL\":\"(.*?)\"")
        r = rx.search(data)

        if not r or len(r.groups()) < 1:
            Logging.error("There was a problem authenticating, no auth landingURL found")
            self.do_login_callback(False)
            return False
        landingURL = r.groups()[0]

        login_payload = {
            "type": "sp",
            "username": username,
            "password": password,
            "secret": secret,
            "trackingId":trackingId,
            "referrer": referrer,
            "landingURL": landingURL,
            "cf":"",
        }

        resp = session.post("https://" + self.auth_server + "/xhr/json/auth.php", data=login_payload, headers=headers)
        resp_json = resp.json()

        if resp_json["status"] != "OK":
            Logging.error("There was a problem authenticating, authentication failed")
            self.do_login_callback(False)
            return False

        self.settings = resp.json()["config"]

        #Get wss settings
        resolver_payload = {
            "client": "24:0:0:" + str(self.settings["version"])
        }

        resp = session.get('http://' + self.settings["aps"]["resolver"]["hostname"], params=resolver_payload, headers=headers)

        resp_json = resp.json()
        wss_hostname = resp_json["ap_list"][0].split(":")[0]

        self.settings["wss"] = "wss://" + wss_hostname + "/"

        return True

    def populate_userdata_callback(self, sp, resp):

        self.username = resp["user"]
        self.country = resp["country"]
        self.account_type = resp["catalogue"]

        # If you're thinking about changing this: don't.
        # I don't want to play cat and mouse with Spotify.
        # I just want an open-library that works for paying
        # users.
        magic = base64.b64encode(resp["catalogue"]) == "cHJlbWl1bQ=="
        self.is_logged_in = True if magic else False

        if not magic:
            Logging.error("Please upgrade to Premium")
            self.disconnect()
        else:
            self.stop_heartbeat = False
            heartbeat_thread = Thread(target=self.heartbeat_handler)
            heartbeat_thread.daemon = True
            heartbeat_thread.start()

        if self.login_callback:
            self.do_login_callback(self.is_logged_in)
        else:
            self.logged_in_marker.set()

    def logged_in(self):
        # Send screen size
        if self.send_command("sp/log", [41, 1, 0, 0, 0, 0], self.log_callback):
            return self.user_info_request(self.populate_userdata_callback)
        else:
            return False

    def login(self):
        Logging.notice("Logging in")
        credentials = self.settings["credentials"][0].split(":", 2)
        credentials[2] = credentials[2].decode("string_escape")
        # credentials_enc = json.dumps(credentials, separators=(',',':'))

        return self.send_command("connect", credentials)

    def do_login_callback(self, result):
        if self.login_callback:
            Thread(target=self.login_callback, args=(self, result)).start()
        else:
            self.logged_in_marker.set()

    def log_callback(self, sp, res):
        return # Nothing to do

    def echo_callback(self, sp, res):
        if res != 'h':
            Logging.notice("Something is not right, echo received: %s" % res)
        return # Nothing to do

    def track_url(self, track, callback=False, retries=3):
        track = self.recurse_alternatives(track)
        if not track:
            return False

        args = ["mp3160", SpotifyUtil.gid2id(track.gid)]
        return self.wrap_request("sp/track_uri", args, callback, retries=retries, timeout=2)

    def parse_metadata(self, sp, resp, callback_data):
        header = mercury_pb2.MercuryReply()
        header.ParseFromString(base64.decodestring(resp[0]))

        if header.status_message == "vnd.spotify/mercury-mget-reply":
            if len(resp) < 2:
                ret = False

            mget_reply = mercury_pb2.MercuryMultiGetReply()
            mget_reply.ParseFromString(base64.decodestring(resp[1]))
            items = []
            for reply in mget_reply.reply:
                if reply.status_code != 200:
                    continue

                item = self.parse_metadata_item(reply.content_type, reply.body)
                items.append(item)
            ret = items
        else:
            ret = self.parse_metadata_item(header.status_message, base64.decodestring(resp[1]))

        self.chain_callback(sp, ret, callback_data)

    def parse_metadata_item(self, content_type, body):
        if content_type == "vnd.spotify/metadata-album":
            obj = metadata_pb2.Album()
        elif content_type == "vnd.spotify/metadata-artist":
            obj = metadata_pb2.Artist()
        elif content_type == "vnd.spotify/metadata-track":
            obj = metadata_pb2.Track()
        else:
            Logging.error("Unrecognised metadata type " + content_type)
            return False

        obj.ParseFromString(body)

        return obj

    def parse_toplist(self, sp, resp, callback_data):
        obj = toplist_pb2.Toplist()
        res = base64.decodestring(resp[1])
        obj.ParseFromString(res)
        self.chain_callback(sp, obj, callback_data)

    def parse_playlist(self, sp, resp, callback_data):
        obj = playlist4changes_pb2.ListDump()
        try:
            res = base64.decodestring(resp[1])
            obj.ParseFromString(res)
        except Exception, e:
            Logging.error("There was a problem while parsing playlist. Message: " + str(e) + ". Resp: " + str(resp))
            obj = False

        self.chain_callback(sp, obj, callback_data)

    def parse_my_music(self, sp, resp, callback_data):
        collection = json.loads(base64.decodestring(resp[1]));
        self.chain_callback(sp, collection, callback_data)

    def chain_callback(self, sp, data, callback_data):
        if len(callback_data) > 1:
            callback_data[0](self, data, callback_data[1:])
        elif len(callback_data) == 1:
            callback_data[0](self, data)

    def is_track_available(self, track, country):
        try:
            track_uri = SpotifyUtil.gid2uri('track', track.gid)
            if not SpotifyUtil.is_track_uri_valid(track_uri):
                return False

            allowed_countries = []
            forbidden_countries = []
            available = True

            for restriction in track.restriction:
                allowed_str = restriction.countries_allowed
                allowed_countries += [allowed_str[i:i+2] for i in range(0, len(allowed_str), 2)]

                forbidden_str = restriction.countries_forbidden
                forbidden_countries += [forbidden_str[i:i+2] for i in range(0, len(forbidden_str), 2)]

                allowed = not restriction.HasField("countries_allowed") or country in allowed_countries
                forbidden = self.country in forbidden_countries and len(forbidden_countries) > 0

                if country in allowed_countries and country in forbidden_countries:
                    allowed = True
                    forbidden = False

                # guessing at names here, corrections welcome
                account_type_map = {
                    "premium":   1,
                    "unlimited": 1,
                    "free":      0
                }

                if self.account_type != None:
                    applicable = account_type_map[self.account_type] in restriction.catalogue
                else:
                    applicable = True

                # enable this to help debug restriction issues
                if False:
                    Logging.debug("*** RESTRICTIONS ***")
                    Logging.debug(str(self.account_type))
                    Logging.debug(str(restriction))
                    Logging.debug(allowed_str)
                    Logging.debug(forbidden_str)
                    Logging.debug("allowed: "+str(allowed))
                    Logging.debug("forbidden: "+str(forbidden))
                    Logging.debug("applicable: "+str(applicable))

                available = True == allowed and False == forbidden and True == applicable
                if available:
                    break

            return available
        except:
            return False

    def recurse_alternatives(self, track, attempted=None, country=None):
        if not attempted:
            attempted = []
        country = self.country if country is None else country
        if self.is_track_available(track, country):
            return track
        else:
            for alternative in track.alternative:
                if self.is_track_available(alternative, country):
                    return alternative
            return False
            #for alternative in track.alternative:
            #    uri = SpotifyUtil.gid2uri("track", alternative.gid)
            #    if uri not in attempted:
            #        attempted += [uri]
            #        subtrack = self.metadata_request(uri)
            #        return self.recurse_alternatives(subtrack, attempted)
            #return False


    def generate_multiget_args(self, metadata_type, requests):
        args = [0]

        if len(requests.request) == 1:
            req = base64.encodestring(requests.request[0].SerializeToString())
            args.append(req)
        else:
            header = mercury_pb2.MercuryRequest()
            header.body = "GET"
            header.uri = "hm://metadata/"+metadata_type+"s"
            header.content_type = "vnd.spotify/mercury-mget-request"

            header_str = base64.encodestring(header.SerializeToString())
            req = base64.encodestring(requests.SerializeToString())
            args.extend([header_str, req])

        return args

    def wrap_request(self, command, args, callback, int_callback=None, retries=3, timeout=None):
        if not callback:
            for attempt in range(0, retries):
                data = WrapAsync(timeout, int_callback, self.send_command, command, args).get_data()
                if data:
                    break
            return data
        else:
            callback = [callback] if type(callback) != list else callback
            if int_callback is not None:
                int_callback = [int_callback] if type(int_callback) != list else int_callback
                callback += int_callback
            return self.send_command(command, args, callback)

    def metadata_request(self, uris, callback=False):
        mercury_requests = mercury_pb2.MercuryMultiGetRequest()

        if type(uris) != list:
            uris = [uris]

        for uri in uris:
            uri_type = SpotifyUtil.get_uri_type(uri)
            if uri_type == "local":
                Logging.warn("Track with URI "+uri+" is a local track, we can't request metadata, skipping")
                continue

            id = SpotifyUtil.uri2id(uri)

            mercury_request = mercury_pb2.MercuryRequest()
            mercury_request.body = "GET"
            mercury_request.uri = "hm://metadata/"+uri_type+"/"+id

            mercury_requests.request.extend([mercury_request])

        args = self.generate_multiget_args(SpotifyUtil.get_uri_type(uris[0]), mercury_requests)

        return self.wrap_request("sp/hm_b64", args, callback, self.parse_metadata)

    def toplist_request(self, toplist_content_type="track", toplist_type="user", username=None, region="global", callback=False):
        if username is None:
            username = self.username

        mercury_request = mercury_pb2.MercuryRequest()
        mercury_request.body = "GET"
        if toplist_type == "user":
            mercury_request.uri = "hm://toplist/toplist/user/"+username
        elif toplist_type == "region":
            mercury_request.uri = "hm://toplist/toplist/region"
            if region is not None and region != "global":
                mercury_request.uri += "/"+region
        else:
            return False
        mercury_request.uri += "?type="+toplist_content_type

        # playlists don't appear to work?
        if toplist_type == "user" and toplist_content_type == "playlist":
            if username != self.username:
                return False
            mercury_request.uri = "hm://socialgraph/suggestions/topplaylists"

        req = base64.encodestring(mercury_request.SerializeToString())

        args = [0, req]

        return self.wrap_request("sp/hm_b64", args, callback, self.parse_toplist)

    def discover_request(self, callback=False):
        story_request = bartender_pb2.StoryRequest()
        story_request.country = self.country;
        story_request.language = "en"
        story_request.device = "web"
        story_request.version = 5
        #story_request.fallback_artist = []
        #story_request.FallbackArtistType = []
        story_request.localtime = calendar.timegm(time.gmtime());
        req_args = base64.encodestring(story_request.SerializeToString())

        mercury_request      = mercury_pb2.MercuryRequest()
        mercury_request.body = "GET"
        mercury_request.uri = "hm://bartender/stories/skip/0/take/100"
        req = base64.encodestring(mercury_request.SerializeToString())

        args = [0, req, req_args]
        return self.wrap_request("sp/hm_b64", args, callback, self.parse_discover)

    def parse_discover(self, sp, resp, callback_data):
        obj = bartender_pb2.StoryList()
        try:
            res = base64.decodestring(resp[1])
            obj.ParseFromString(res)
        except Exception, e:
            Logging.error("There was a problem while parsing discover info. Message: " + str(e) + ". Resp: " + str(resp))
            obj = False
        self.chain_callback(sp, obj, callback_data)

    def radio_stations_request(self, callback=False):
        mercury_request = mercury_pb2.MercuryRequest()
        mercury_request.body = "GET"
        mercury_request.uri = "hm://radio/stations"
        req = base64.encodestring(mercury_request.SerializeToString())

        args = [0, req]
        return self.wrap_request("sp/hm_b64", args, callback, self.parse_radio_stations)

    def parse_radio_stations(self, sp, resp, callback_data):
        obj = radio_pb2.StationList()
        try:
            res = base64.decodestring(resp[1])
            obj.ParseFromString(res)
        except Exception, e:
            Logging.error("There was a problem while parsing radio stations info. Message: " + str(e) + ". Resp: " + str(resp))
            obj = False
        self.chain_callback(sp, obj, callback_data)

    def radio_genres_request(self, callback=False):
        mercury_request = mercury_pb2.MercuryRequest()
        mercury_request.body = "GET"
        mercury_request.uri = "hm://radio/genres/"
        req = base64.encodestring(mercury_request.SerializeToString())

        args = [0, req]
        return self.wrap_request("sp/hm_b64", args, callback, self.parse_radio_genres)

    def parse_radio_genres(self, sp, resp, callback_data):
        obj = radio_pb2.GenreList()
        try:
            res = base64.decodestring(resp[1])
            obj.ParseFromString(res)
        except Exception, e:
            Logging.error("There was a problem while parsing radio genre list info. Message: " + str(e) + ". Resp: " + str(resp))
            obj = False
        self.chain_callback(sp, obj, callback_data)

    # Station uri can be a track, artist, or genre (spotify:genre:[genre_id])
    def radio_tracks_request(self, stationUri, stationId=None, salt=None, num_tracks=20, callback=False):
        if salt == None:
            max32int = pow(2,31) - 1
            salt     = randint(1,max32int)

        if stationId == None:
            stationId = uuid.uuid4().hex

        radio_request           = radio_pb2.RadioRequest()
        radio_request.salt      = salt
        radio_request.length    = num_tracks
        radio_request.stationId = stationId
        radio_request.uris.append(stationUri)
        req_args = base64.encodestring(radio_request.SerializeToString())

        mercury_request      = mercury_pb2.MercuryRequest()
        mercury_request.body = "GET"
        mercury_request.uri  = "hm://radio/"
        req = base64.encodestring(mercury_request.SerializeToString())

        args = [0, req, req_args]
        return self.wrap_request("sp/hm_b64", args, callback, self.parse_radio_tracks)

    def parse_radio_tracks(self, sp, resp, callback_data):
        obj = radio_pb2.Tracks()
        try:
            res = base64.decodestring(resp[1])
            obj.ParseFromString(res)
        except Exception, e:
            Logging.error("There was a problem while parsing radio tracks. Message: " + str(e) + ". Resp: " + str(resp))
            obj = False
        self.chain_callback(sp, obj, callback_data)

    def playlists_request(self, user, fromnum=0, num=100, callback=False):
        if num > 100:
            Logging.error("You may only request up to 100 playlists at once")
            return False

        mercury_request = mercury_pb2.MercuryRequest()
        mercury_request.body = "GET"
        mercury_request.uri = "hm://playlist/user/"+user+"/rootlist?from=" + str(fromnum) + "&length=" + str(num)
        req = base64.encodestring(mercury_request.SerializeToString())

        args = [0, req]

        return self.wrap_request("sp/hm_b64", args, callback, self.parse_playlist)

    def playlist_request(self, uri, fromnum=0, num=100, callback=False):
        playlist_uri = uri.replace(":", "/")[8:] 
        
        mercury_request = mercury_pb2.MercuryRequest()
        mercury_request.body = "GET"
        mercury_request.uri = "hm://playlist/" + playlist_uri + "?from=" + str(fromnum) + "&length=" + str(num)

        req = base64.encodestring(mercury_request.SerializeToString())
        args = [0, req]

        return self.wrap_request("sp/hm_b64", args, callback, self.parse_playlist)

    def my_music_request(self, type="albums", callback=False):
        if type == "albums":
            action = "albumscoverlist"
            extras = ""
        elif type == "artists":
            action = "artistscoverlist"
            extras = "?includefollowedartists=true"
        else:
            return []

        mercury_request = mercury_pb2.MercuryRequest()
        mercury_request.body = "GET"
        mercury_request.uri = "hm://collection-web/v1/" + self.username + "/" + action + extras

        req = base64.encodestring(mercury_request.SerializeToString())
        args = [0, req]

        return self.wrap_request("sp/hm_b64", args, callback, self.parse_my_music)

    def playlist_op_track(self, playlist_uri, track_uri, op, callback=False):
        playlist = playlist_uri.split(":")

        if playlist_uri == "rootlist":
            user = self.username
            playlist_id = "rootlist"
        else:
            user = playlist[2]
            if playlist[3] == "starred":
                playlist_id = "starred"
            else:
                playlist_id = "playlist/"+playlist[4]

        mercury_request = mercury_pb2.MercuryRequest()
        mercury_request.body = op
        mercury_request.uri = "hm://playlist/user/"+user+"/" + playlist_id + "?syncpublished=1"
        req = base64.encodestring(mercury_request.SerializeToString())
        args = [0, req, base64.encodestring(track_uri)]
        return self.wrap_request("sp/hm_b64", args, callback)

    def playlist_add_track(self, playlist_uri, track_uri, callback=False):
        return self.playlist_op_track(playlist_uri, track_uri, "ADD", callback)

    def playlist_remove_track(self, playlist_uri, track_uri, callback=False):
        return self.playlist_op_track(playlist_uri, track_uri, "REMOVE", callback)

    def set_starred(self, track_uri, starred=True, callback=False):
        if starred:
            return self.playlist_add_track("spotify:user:"+self.username+":starred", track_uri, callback)
        else:
            return self.playlist_remove_track("spotify:user:"+self.username+":starred", track_uri, callback)

    def playlist_op(self, op, path, optype="update", name=None, index=None, callback=False):
        mercury_request = mercury_pb2.MercuryRequest()
        mercury_request.body = op
        mercury_request.uri = "hm://" + path

        req = base64.encodestring(mercury_request.SerializeToString())

        op = playlist4ops_pb2.Op()
        if optype == "update":
            op.kind = playlist4ops_pb2.Op.UPDATE_LIST_ATTRIBUTES
            op.update_list_attributes.new_attributes.values.name = name
        elif optype == "remove":
            op.kind = playlist4ops_pb2.Op.REM
            op.rem.fromIndex = index
            op.rem.length = 1

        mercury_request_payload = mercury_pb2.MercuryRequest()
        mercury_request_payload.uri = op.SerializeToString()

        payload = base64.encodestring(mercury_request_payload.SerializeToString())

        args = [0, req, payload]
        return self.wrap_request("sp/hm_b64", args, callback, self.new_playlist_callback)

    def new_playlist(self, name, callback=False):
        return self.playlist_op("PUT", "playlist/user/"+self.username, name=name, callback=callback)

    def rename_playlist(self, playlist_uri, name, callback=False):
        path = "playlist/user/"+self.username+"/playlist/"+playlist_uri.split(":")[4]+"?syncpublished=true"
        return self.playlist_op("MODIFY", path, name=name, callback=callback)

    def remove_playlist(self, playlist_uri, callback=False):
        return self.playlist_op_track("rootlist", playlist_uri, "REMOVE", callback=callback)
        #return self.playlist_op("REMOVE", "playlist/user/"+self.username+"/rootlist?syncpublished=true",
                                #optype="remove", index=index, callback=callback)

    def new_playlist_callback(self, sp, data, callback_data):
        try:
            reply = playlist4service_pb2.CreateListReply()
            reply.ParseFromString(base64.decodestring(data[1]))
        except:
            self.chain_callback(sp, False, callback_data)

        mercury_request = mercury_pb2.MercuryRequest()
        mercury_request.body = "ADD"
        mercury_request.uri = "hm://playlist/user/"+self.username+"/rootlist?add_first=1&syncpublished=1"
        req = base64.encodestring(mercury_request.SerializeToString())
        args = [0, req, base64.encodestring(reply.uri)]

        self.chain_callback(sp, reply.uri, callback_data)
        return self.send_command("sp/hm_b64", args)

    def search_request(self, query, query_type="all", max_results=50, offset=0, callback=False):
        if max_results > 50:
            Logging.warn("Maximum of 50 results per request, capping at 50")
            max_results = 50

        search_types = {
            "tracks": 1,
            "albums": 2,
            "artists": 4,
            "playlists": 8

        }

        query_type = [k for k, v in search_types.items()] if query_type == "all" else query_type
        query_type = [query_type] if type(query_type) != list else query_type
        query_type = reduce(operator.or_, [search_types[type_name] for type_name in query_type if type_name in search_types])

        args = [query, query_type, max_results, offset]

        return self.wrap_request("sp/search", args, callback)

    def user_info_request(self, callback=False):
        return self.wrap_request("sp/user_info", [], callback)

    def heartbeat(self):
        return self.send_command("sp/echo", ["h"], self.echo_callback)

    def send_track_end(self, lid, track_uri, ms_played, callback=False):
        ms_played = int(ms_played)
        ms_played_union = ms_played
        n_seeks_forward = 0
        n_seeks_backward = 0
        ms_seeks_forward = 0
        ms_seeks_backward = 0
        ms_latency = 100
        play_context = "unknown"
        source_start = "unknown"
        source_end = "unknown"
        reason_start = "unknown"
        reason_end = "unknown"
        referrer = "unknown"
        referrer_version = "0.1.0"
        referrer_vendor = "com.spotify"
        max_continuous = ms_played

        args = [
            lid,
            ms_played, ms_played_union,
            n_seeks_forward, n_seeks_backward,
            ms_seeks_forward, ms_seeks_backward,
            ms_latency,
            track_uri,
            play_context,
            source_start, source_end,
            reason_start, reason_end,
            referrer, referrer_version, referrer_vendor,
            max_continuous,
            "none",
            "na"
        ]

        return self.send_command("sp/track_end", args, callback)

    def send_track_event(self, lid, event, ms_where, callback=False):
        if event == "pause" or event == "stop":
            ev_n = 4
        elif event == "unpause" or "continue" or "play":
            ev_n = 3
        else:
            return False

        return self.send_command("sp/track_event", [lid, ev_n, int(ms_where)], callback)

    def send_track_progress(self, lid, ms_played, callback=False):
        source_start = "unknown"
        reason_start = "unknown"
        ms_latency = 100
        play_context = "unknown"
        display_track = ""
        referrer = "unknown"
        referrer_version = "0.1.0"
        referrer_vendor = "com.spotify"

        args = [
            lid,
            source_start,
            reason_start,
            int(ms_played),
            int(ms_latency),
            play_context,
            display_track,
            referrer, referrer_version, referrer_vendor
        ]

        return self.send_command("sp/track_progress", args, callback)

    def send_command(self, name, args=None, callback=None):
        if not args:
            args = []
        msg = {
            "name": name,
            "id": str(self.seq),
            "args": args
        }

        if callback is not None:
            self.cmd_callbacks[self.seq] = callback
        self.seq += 1

        return self.send_string(msg)

    def send_string(self, msg):
        if self.ws is None or self.ws.stream is None:
            Logging.debug("Message send but connection is not active, ignoring: [%s]" % msg)
            return False

        if self.disconnecting and not self.connecting:
            Logging.debug("Message send while disconnecting, ignoring: [%s]" % msg)
            return False

        msg_enc = json.dumps(msg, separators=(',', ':'))
        Logging.debug("sent " + msg_enc)
        try:
            with self.ws_lock:
                self.ws.send(msg_enc)
        except SSLError:
            Logging.notice("SSL error, attempting to continue")

        return True

    def recv_packet(self, msg):
        if self.disconnecting and not self.connecting:
            Logging.debug("Message recv while disconnecting, ignoring: [%s]" % msg)
            return

        Logging.debug("recv " + str(msg))
        packet = json.loads(str(msg))
        if "error" in packet:
            self.handle_error(packet)
            return
        elif "message" in packet:
            self.handle_message(packet["message"])
        elif "id" in packet:
            pid = packet["id"]
            if pid in self.cmd_callbacks:
                callback = self.cmd_callbacks[pid]

                if not callback:
                    Logging.debug("No callback was requested for command " + str(pid) + ", ignoring")
                elif type(callback) == list:
                    if len(callback) > 1:
                        callback[0](self, packet["result"], callback[1:])
                    else:
                        callback[0](self, packet["result"])
                else:
                    callback(self, packet["result"])

                self.cmd_callbacks.pop(pid)
            else:
                Logging.debug("Unhandled command response with id " + str(pid))

    def work(self, payload):
        Logging.debug("Got do_work message, payload: " + payload)
        try:
            ctx = execjs.compile(WORK_RUNNER % payload)
            result = ctx.eval('main.run.call(main)')
            Logging.debug('Work result: %s' % result)

            return self.send_command("sp/work_done", result, self.work_callback)
        except Exception, e:
            Logging.error("There was a problem while do_work. Message: " + str(e))
            return False

    def work_callback(self, sp, resp):
        Logging.debug("Got ack for message reply")

    def send_pong(self, ping):
        rest_ping = ping.replace(" ","-")
        pong = "undefined 0"
        Logging.debug("Obtaining pong for ping [%s]" % rest_ping)
        try:
            r = requests.get("http://ping-pong.spotify.nodestuff.net/%s" % rest_ping)
            if r.status_code == 200:
                result = r.json()
                if result['status'] == 100:
                    pong = result['pong'].replace("-"," ")

            Logging.debug('received flash ping %s, sending pong: %s' % (ping, pong))
            return self.send_command('sp/pong_flash2', [pong])
        except Exception, e:
            Logging.debug("There was a problem while obtaining pong. Message: " + str(e))
            return False

    def handle_message(self, msg):
        cmd = msg[0]

        payload = None
        if len(msg) > 1:
            payload = msg[1]

        if cmd == "do_work":
            self.work(payload)

        if cmd == "ping_flash2":
            self.send_pong(payload)

        if cmd == "login_complete":
            self.logged_in()

    def handle_error(self, err):
        if len(err) < 2:
            Logging.error("Unknown error "+str(err))

        major = err["error"][0]
        minor = err["error"][1]

        major_err = {
            8: "Rate request error",
            12: "Track error",
            13: "Hermes error",
            14: "Hermes service error",
        }

        minor_err = {
            1: "failed to send to backend",
            8: "rate limited",
            408: "timeout",
            429: "too many requests",
        }

        if major in major_err:
            major_str = major_err[major]
        else:
            major_str = "unknown (" + str(major) + ")"

        if minor in minor_err:
            minor_str = minor_err[minor]
        else:
            minor_str = "unknown (" + str(minor) + ")"

        if minor == 0:
            Logging.error(major_str)
        else:
            Logging.error(major_str + " - " + minor_str)

    def heartbeat_handler(self):
        self.heartbeat_marker.clear()
        while not self.stop_heartbeat:
            self.heartbeat()
            self.heartbeat_marker.wait(timeout=45)

    def connect(self, username, password, timeout=20):
        can_connect = self.connecting_marker.acquire(blocking=False)
        try:
            if not can_connect:
                Logging.debug("Already connecting, nothing to do. Waiting to previously connect to finish")
                self.connecting_marker.acquire()
                return self.is_logged_in
            else:
                self.connecting = True
                try:
                    if self.settings is None:
                        if not self.auth(username, password):
                            return False
                        self.username = username
                        self.password = password

                    Logging.notice("Connecting to "+self.settings["wss"])
                    with self.ws_lock:
                        headers = [
                            ["Origin", "https://play.spotify.com"],
                            ["User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/31.0.1650.63 Safari/537.36"]
                        ]
                        self.ws = SpotifyClient(url=self.settings["wss"], headers=headers)
                        self.ws.set_api(self)
                        self.ws.daemon = True
                        self.ws.connect()

                    if not self.login_callback:
                        try:
                            self.logged_in_marker.wait(timeout=timeout)
                            return self.is_logged_in
                        except Exception, e:
                            Logging.error("There was a timeout while connecting to spotify. Message: " + str(e))
                            return False

                except Exception, e:
                    Logging.error("There was a problem while connecting to spotify. Message: " + str(e))
                    self.disconnect()
                    return False
                finally:
                    self.connecting    = False
                    self.disconnecting = False
        finally:
            self.connecting_marker.release()

    def set_log_level(self, level):
        Logging.log_level = level

    def shutdown(self):
        can_shutdown = self.shutdown_marker.acquire(blocking=False)
        try:
            # If there is a shutdown in process, just wait until it finishes, but don't raise another one
            if not can_shutdown:
                self.shutdown_marker.acquire()
            else:
                self.stop_heartbeat = True
                self.heartbeat_marker.set()
                self.disconnect()
        finally:
            self.shutdown_marker.release()

    def reconnect(self, username, password):
        can_reconnect = self.reconnect_marker.acquire(blocking=False)
        try:
            if not can_reconnect:
                self.reconnect_marker.acquire()
            else:
                self.disconnecting = True
                try:
                    Logging.debug("Disconnecting...")
                    self.shutdown()

                    Logging.debug("Restarting...")
                    self.start()

                    Logging.debug("Conecting...")
                    self.connect(username, password)
                except Exception, e:
                    Logging.error("There was a problem while reconnecting to spotify. Message: " + str(e))
                finally:
                    self.disconnecting = False
        finally:
            self.reconnect_marker.release()

        return self.is_logged_in

    def disconnect(self):
        can_disconnect = self.disconnect_marker.acquire(blocking=False)
        try:
            if not can_disconnect:
                self.disconnect_marker.acquire()
            else:
                if self.ws is not None:
                    if self.ws.stream is not None:
                        self.ws.close()
                    self.ws = None
        finally:
            self.disconnect_marker.release()
