# coding: utf-8

from .common import InfoExtractor
from ..utils import (
    std_headers,
    try_get,
    ExtractorError,
)

import json
import random
import re


class WPPilotBaseIE(InfoExtractor):
    # _NETRC_MACHINE = 'wppilot'

    # _VIDEO_URL = 'https://pilot.wp.pl/api/v1/channel/%s'
    _VIDEO_GUEST_URL = 'https://pilot.wp.pl/api/v1/guest/channel/%s'
    # _VIDEO_CLOSE_URL = 'https://pilot.wp.pl/api/v1/channels/close'
    # _LOGIN_URL = 'https://pilot.wp.pl/api/v1/user_auth/login'
    _WEBPAGE_URL = 'https://pilot.wp.pl/tv/'

    # _HEADERS_ATV = {
    #     'User-Agent': 'ExoMedia 4.3.0 (43000) / Android 8.0.0 / foster_e',
    #     'Accept': 'application/json',
    #     'X-Version': 'pl.videostar|3.25.0|Android|26|foster_e',
    #     'Content-Type': 'application/json; charset=UTF-8',
    # }
    _HEADERS_WEB = {
        'Content-Type': 'application/json; charset=UTF-8',
        'Referer': 'https://pilot.wp.pl/tv/',
    }

    ''' WP requires a recaptcha token now for auth
    def _login(self):
        username, password = self._get_login_info()
        if not username:
            return None

        login = self._download_json(
            self._LOGIN_URL, None, 'Logging in', 'Unable to log in',
            headers=self._HEADERS_ATV,
            data=bytes(json.dumps({
                'device': 'android_tv',
                'login': username,
                'password': password,
            }).encode('utf-8')))

        error = try_get(login, lambda x: x['_meta']['error']['name'])
        if error:
            raise ExtractorError(f'WP login error: "{error}"')
    '''

    def _get_channel_list(self, cache=True):
        if cache is True:
            cache_res = self._downloader.cache.load('wppilot', 'channel-list')
            if cache_res:
                return cache_res, True
        webpage = self._download_webpage(self._WEBPAGE_URL, None, 'Downloading webpage')
        page_data_base_url = self._search_regex(
            r'<script src="(https://wp-pilot-gatsby\.wpcdn\.pl/v[\d.-]+/desktop)',
            webpage, 'gatsby build version') + '/page-data'
        page_data = self._download_json(f'{page_data_base_url}/tv/page-data.json', None, 'Downloading page data')
        for qhash in page_data['staticQueryHashes']:
            qhash_content = self._download_json(
                f'{page_data_base_url}/sq/d/{qhash}.json', None,
                'Searching for channel list')
            channel_list = try_get(qhash_content, lambda x: x['data']['allChannels']['nodes'])
            if channel_list is None:
                continue
            self._downloader.cache.store('wppilot', 'channel-list', channel_list)
            return channel_list, False
        raise ExtractorError('Unable to find the channel list')

    def _parse_channel(self, chan):
        thumbnails = []
        for key in ('thumbnail', 'thumbnail_mobile', 'icon'):
            if chan.get(key):
                thumbnails.append({
                    'id': key,
                    'url': chan[key],
                })
        return {
            'id': str(chan['id']),
            'title': chan['name'],
            'is_live': True,
        }


class WPPilotIE(WPPilotBaseIE):
    _VALID_URL = r'(?:https?://pilot\.wp\.pl/tv/?#|wppilot:)(?P<id>[a-z\d-]+)'
    IE_NAME = 'wppilot'

    _TESTS = [{
        'url': 'https://pilot.wp.pl/tv/#telewizja-wp-hd',
        'info_dict': {
            'id': '158',
            'ext': 'mp4',
            'title': 'Telewizja WP HD',
        },
        'params': {
            'format': 'bestvideo',
        },
    }, {
        # audio only
        'url': 'https://pilot.wp.pl/tv/#radio-nowy-swiat',
        'info_dict': {
            'id': '238',
            'ext': 'm4a',
            'title': 'Radio Nowy Świat',
        },
        'params': {
            'format': 'bestaudio',
        },
    }, {
        'url': 'wppilot:9',
        'only_matching': True,
    }]

    def _get_channel(self, id_or_slug):
        video_list, video_list_cached = self._get_channel_list(cache=True)
        key = 'id' if re.match(r'^\d+$', id_or_slug) else 'slug'
        for video in video_list:
            if video.get(key) == id_or_slug:
                return self._parse_channel(video)
        # if cached channel not found, download and retry
        if video_list_cached:
            video_list, _ = self._get_channel_list(cache=False)
            for video in video_list:
                if video.get(key) == id_or_slug:
                    return self._parse_channel(video)
        raise ExtractorError('Channel not found')

    def _real_extract(self, url):
        video_id = self._match_id(url)

        channel = self._get_channel(video_id)
        video_id = str(channel['id'])
        video = self._download_json(
            self._VIDEO_GUEST_URL % video_id, video_id, query={
                'device_type': 'web',
            }, headers=self._HEADERS_WEB)

        # stream_token = try_get(video, lambda x: x['_meta']['error']['info']['stream_token'])
        # if stream_token:
        #     close = self._download_json(
        #         self._VIDEO_CLOSE_URL, video_id, 'Invalidating previous stream session',
        #         headers=self._HEADERS_ATV,
        #         data=bytes(json.dumps({
        #             'channelId': video_id,
        #             't': stream_token,
        #         }).encode('utf-8')))
        #     if try_get(close, lambda x: x['data']['status']) == 'ok':
        #         return self.url_result('wppilot:%s' % video_id, ie=WPPilotIE.ie_key())

        formats = []

        for fmt in video['data']['stream_channel']['streams']:
            # MPD does not work for some reason
            # if fmt['type'] == 'dash@live:abr':
            #     formats.extend(
            #         self._extract_mpd_formats(
            #             random.choice(fmt['url']), video_id))
            if fmt['type'] == 'hls@live:abr':
                formats.extend(
                    self._extract_m3u8_formats(
                        random.choice(fmt['url']),
                        video_id))

        self._sort_formats(formats)

        channel['formats'] = formats
        return channel


class WPPilotChannelsIE(WPPilotBaseIE):
    _VALID_URL = r'(?:https?://pilot\.wp\.pl/(?:tv/?)?(?:\?[^#]*)?#?|wppilot:)$'
    IE_NAME = 'wppilot:channels'

    _TESTS = [{
        'url': 'wppilot:',
        'info_dict': {
            'id': 'wppilot',
            'title': 'WP Pilot',
        },
        'playlist_mincount': 100,
    }, {
        'url': 'https://pilot.wp.pl/',
        'only_matching': True,
    }]

    def _entries(self):
        channel_list, _ = self._get_channel_list()
        for chan in channel_list:
            entry = self._parse_channel(chan)
            entry.update({
                '_type': 'url_transparent',
                'url': f'wppilot:{chan["id"]}',
                'ie_key': WPPilotIE.ie_key(),
            })
            yield entry

    def _real_extract(self, url):
        return self.playlist_result(self._entries(), 'wppilot', 'WP Pilot')
