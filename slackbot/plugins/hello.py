# coding: UTF-8
import re

from slackbot.bot import respond_to, listen_to, run_at_times


@respond_to('hello$', re.IGNORECASE)
def hello_reply(message):
    message.reply('hello sender!')


@respond_to('^reply_webapi$')
def hello_webapi(message):
    message.reply_webapi('hello there!', attachments=[{
        'fallback': 'test attachment',
        'fields': [
            {
                'title': 'test table field',
                'value': 'test table value',
                'short': True
            }
        ]
    }])


@respond_to('^reply_webapi_not_as_user$')
def hello_webapi_not_as_user(message):
    message.reply_webapi('hi!', as_user=False)


@respond_to('hello_formatting')
def hello_reply_formatting(message):
    # Format message with italic style
    message.reply('_hello_ sender!')


@listen_to('hello$')
def hello_send(message):
    message.send('hello channel!')


@listen_to('hello_decorators')
@respond_to('hello_decorators')
def hello_decorators(message):
    message.send('hello!')

@listen_to('hey!')
def hey(message):
    message.react('eggplant')


@respond_to(u'你好')
def hello_unicode_message(message):
    message.reply(u'你好!')


@listen_to('start a thread')
def start_thread(message):
    message.reply('I started a thread', in_thread=True)


RUN_AT_TIMES = {'start': False, 'channel': None}


@respond_to('start run at times test')
@listen_to('start run at times test')
def start_run_at_times_test(message):
    print("---------- start run at times test! -----------")
    RUN_AT_TIMES['start'] = True
    RUN_AT_TIMES['channel'] = message._body['channel']


@run_at_times(run_once_at=20)
def run_at_times1(client):
    if RUN_AT_TIMES['start']:
        client.rtm_send_message(RUN_AT_TIMES['channel'], 'Run at times function works!')
    RUN_AT_TIMES['start'] = False
