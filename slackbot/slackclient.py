# -*- coding: utf-8 -*-

from __future__ import print_function, absolute_import
import os
import json
import logging
import time
from ssl import SSLError

import slacker
from six import iteritems

from websocket import (
    create_connection, WebSocketException, WebSocketConnectionClosedException
)

from slackbot.utils import to_utf8, get_http_proxy

logger = logging.getLogger(__name__)


class SlackClient(object):
    def __init__(self, token, timeout=None, bot_icon=None, bot_emoji=None, connect=True):
        self.token = token
        self.bot_icon = bot_icon
        self.bot_emoji = bot_emoji
        self.username = None
        self.domain = None
        self.login_data = None
        self.websocket = None
        self.users = {}
        self.channels = {}
        self.dm_channels = {}  # map user id to direct message channel id
        self.connected = False
        if timeout is None:
            self.webapi = slacker.Slacker(self.token)
        else:
            self.webapi = slacker.Slacker(self.token, timeout=timeout)

        if connect:
            self.rtm_connect()

    def rtm_connect(self):
        reply = self.webapi.rtm.start().body
        time.sleep(1)
        self.parse_slack_login_data(reply)

    def reconnect(self):
        while True:
            try:
                self.rtm_connect()
                logger.warning('reconnected to slack rtm websocket')
                return
            except Exception as e:
                logger.exception('failed to reconnect: %s', e)
                time.sleep(5)

    def parse_slack_login_data(self, login_data):
        self.login_data = login_data
        self.domain = self.login_data['team']['domain']
        self.username = self.login_data['self']['name']
        self.parse_user_data(login_data['users'])
        self.parse_channel_data(login_data['channels'])
        self.parse_channel_data(login_data['groups'])
        self.parse_channel_data(login_data['ims'])

        proxy, proxy_port, no_proxy = get_http_proxy(os.environ)

        self.websocket = create_connection(self.login_data['url'], http_proxy_host=proxy,
                                           http_proxy_port=proxy_port, http_no_proxy=no_proxy)

        self.websocket.sock.setblocking(0)

    def parse_channel_data(self, channel_data):
        self.channels.update({c['id']: c for c in channel_data})
        # pre-load direct message channels
        for c in channel_data:
            if 'user' in c:
                self.dm_channels[c['user']] = c['id']

    def parse_user_data(self, user_data):
        self.users.update({u['id']: u for u in user_data})

    def send_to_websocket(self, data):
        """Send (data) directly to the websocket."""
        data = json.dumps(data)
        self.websocket.send(data)

    def ping(self):
        self.send_to_websocket({'type': 'ping'})

    def websocket_safe_read(self):
        """Returns data if available, otherwise ''. Newlines indicate multiple messages """
        data = ''
        while True:
            try:
                data += '{0}\n'.format(self.websocket.recv())
            except WebSocketException as e:
                if isinstance(e, WebSocketConnectionClosedException):
                    logger.warning('lost websocket connection, try to reconnect now')
                else:
                    logger.warning('websocket exception: %s', e)
                self.reconnect()
            except Exception as e:
                if isinstance(e, SSLError) and e.errno == 2:
                    pass
                else:
                    logger.warning('Exception in websocket_safe_read: %s', e)
                return data.rstrip()

    def rtm_read(self):
        json_data = self.websocket_safe_read()
        data = []
        if json_data != '':
            for d in json_data.split('\n'):
                data.append(json.loads(d))
        return data

    def rtm_send_message(self, channel, message, attachments=None, thread_ts=None):
        channel = self._channelify(channel)
        message_json = {
            'type': 'message',
            'channel': channel,
            'text': message,
            'attachments': attachments,
            'thread_ts': thread_ts,
            }
        self.send_to_websocket(message_json)

    def upload_file(self, channel, fname, fpath, comment):
        channel = self._channelify(channel)
        fname = fname or to_utf8(os.path.basename(fpath))
        self.webapi.files.upload(fpath,
                                 channels=channel,
                                 filename=fname,
                                 initial_comment=comment)

    def upload_content(self, channel, fname, content, comment):
        self.webapi.files.upload(None,
                                 channels=channel,
                                 content=content,
                                 filename=fname,
                                 initial_comment=comment)

    def send_message(self, channel, message, attachments=None, as_user=True, thread_ts=None):
        channel = self._channelify(channel)
        self.webapi.chat.post_message(
                channel,
                message,
                username=self.login_data['self']['name'],
                icon_url=self.bot_icon,
                icon_emoji=self.bot_emoji,
                attachments=attachments,
                as_user=as_user,
                thread_ts=thread_ts)

    def get_channel(self, channel_id):
        return Channel(self, self.channels[channel_id])

    def get_dm_channel(self, user_id):
        """Get the direct message channel for the given user id, opening
        one if necessary."""
        if user_id not in self.users:
            raise ValueError("Expected valid user_id, have no user '%s'" % (
                user_id,))

        if user_id in self.dm_channels:
            return self.dm_channels[user_id]

        # open a new channel
        resp = self.webapi.im.open(user_id)
        if not resp.body["ok"]:
            raise ValueError("Could not open DM channel: %s" % resp.body)

        self.dm_channels[user_id] = resp.body['channel']['id']

        return self.dm_channels[user_id]

    def _channelify(self, s):
        """Turn a string into a channel.

        * Given a channel id, return that same channel id.
        * Given a channel name, return the channel id.
        * Given a user id, return the direct message channel with that user,
        opening a new one if necessary.
        * Given a user name, do the same as for a user id.

        Raise a ValueError otherwise."""
        if s in self.channels:
            return s

        channel_id = self.find_channel_by_name(s)
        if channel_id:
            return channel_id

        if s in self.users:
            return self.get_dm_channel(s)

        user_id = self.find_user_by_name(s)
        if user_id:
            return self.get_dm_channel(user_id)

        raise ValueError("Could not turn '%s' into any kind of channel name" % (
            user_id))

    def find_channel_by_name(self, channel_name):
        for channel_id, channel in iteritems(self.channels):
            try:
                name = channel['name']
            except KeyError:
                name = self.users[channel['user']]['name']
            if name == channel_name:
                return channel_id

    def get_user(self, user_id):
        return self.users.get(user_id)

    def find_user_by_name(self, username):
        for userid, user in iteritems(self.users):
            if user['name'] == username:
                return userid

    def react_to_message(self, emojiname, channel, timestamp):
        self.webapi.reactions.add(
            name=emojiname,
            channel=channel,
            timestamp=timestamp)


class SlackConnectionError(Exception):
    pass


class Channel(object):
    def __init__(self, slackclient, body):
        self._body = body
        self._client = slackclient

    def __eq__(self, compare_str):
        name = self._body['name']
        cid = self._body['id']
        return name == compare_str or "#" + name == compare_str or cid == compare_str

    def upload_file(self, fname, fpath, initial_comment=''):
        self._client.upload_file(
            self._body['id'],
            to_utf8(fname),
            to_utf8(fpath),
            to_utf8(initial_comment)
        )

    def upload_content(self, fname, content, initial_comment=''):
        self._client.upload_content(
            self._body['id'],
            to_utf8(fname),
            to_utf8(content),
            to_utf8(initial_comment)
        )
