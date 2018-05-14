# -*- coding: utf-8 -*-
from __future__ import absolute_import
import imp
import importlib
import logging
import re
import time
from glob import glob
from six.moves import _thread
from slackbot import settings
from slackbot.manager import PluginsManager
from slackbot.slackclient import SlackClient
from slackbot.dispatcher import MessageDispatcher

logger = logging.getLogger(__name__)


class Bot(object):
    def __init__(self):
        self._client = SlackClient(
            settings.API_TOKEN,
            timeout=settings.TIMEOUT if hasattr(settings,
                                                'TIMEOUT') else None,
            bot_icon=settings.BOT_ICON if hasattr(settings,
                                                  'BOT_ICON') else None,
            bot_emoji=settings.BOT_EMOJI if hasattr(settings,
                                                    'BOT_EMOJI') else None
        )
        self._plugins = PluginsManager()
        self._dispatcher = MessageDispatcher(self._client, self._plugins,
                                             settings.ERRORS_TO)

    def run(self):
        self._plugins.init_plugins()
        self._dispatcher.start()
        if not self._client.connected: 
            self._client.rtm_connect()
            
        _thread.start_new_thread(self._keepactive, tuple())
        logger.info('connected to slack RTM api')
        self._dispatcher.loop()

    def _keepactive(self):
        logger.info('keep active thread started')
        while True:
            time.sleep(30 * 60)
            self._client.ping()


def respond_to(matchstr, flags=0):
    def wrapper(func):
        PluginsManager.commands['respond_to'][
            re.compile(matchstr, flags)] = func
        logger.info('registered respond_to plugin "%s" to "%s"', func.__name__,
                    matchstr)
        return func

    return wrapper


def listen_to(matchstr, flags=0):
    def wrapper(func):
        PluginsManager.commands['listen_to'][
            re.compile(matchstr, flags)] = func
        logger.info('registered listen_to plugin "%s" to "%s"', func.__name__,
                    matchstr)
        return func

    return wrapper


def run_at_times(**kwargs):
    """
    Decorator to run a function once a given number of seconds.
    Takes run_once_at int parameter in seconds.
    The decorated function must take one parameter, a SlackClient instance.
    """
    if kwargs:
        if 'run_once_at' in kwargs:
            run_once_at = kwargs['run_once_at']
        else:
            # default to 60s if no run_on_once is given
            run_once_at = 60

    def wrapper(func):
        func.last_run = None
        func.run_once_at = run_once_at
        PluginsManager.run_at_times_commands.append(func)
        logger.info('registered run at given times plugin "%s"', func.__name__)
        return func
    return wrapper


# def default_reply(matchstr=r'^.*$', flags=0):
def default_reply(*args, **kwargs):
    """
    Decorator declaring the wrapped function to the default reply hanlder.

    May be invoked as a simple, argument-less decorator (i.e. ``@default_reply``) or
    with arguments customizing its behavior (e.g. ``@default_reply(matchstr='pattern')``).
    """
    invoked = bool(not args or kwargs)
    matchstr = kwargs.pop('matchstr', r'^.*$')
    flags = kwargs.pop('flags', 0)

    if not invoked:
        func = args[0]

    def wrapper(func):
        PluginsManager.commands['default_reply'][
            re.compile(matchstr, flags)] = func
        logger.info('registered default_reply plugin "%s" to "%s"', func.__name__,
                    matchstr)
        return func

    return wrapper if invoked else wrapper(func)
