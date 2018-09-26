import time 
import util
import traceback
import slackclient 
from pprint import pprint
import logging
import traceback
import ujson as json
import socket
import websocket


def make_uid2name(data):
    rv = {}
    for user in data["members"]:
        try:
            uid = user['id']
            name = user['profile']['real_name']
            rv[uid] = name
        except KeyError:
            print(user)
    return rv


def response_is_message(r):
    '''
    Checks if a response sent by slack via rtm connection is a message, as
    opposed to an emoticon event or a ping or any variety of other things.
    '''
    if {'type', 'channel', 'text', 'user'}.issubset(set(r.keys())):    
        if r['type'] == 'message':
            if r['text']:
                return True
    return False
            



class ClientHandler(object):
    '''
    Code that filters out stuff we get from the Slack rtm api, passes messages
    along to the "brain" object, and sends the messages back to slack.
    '''
    def __init__(self, token, brain, name, log_text=False):
        '''
        Brain is an object that implements 
            brain.handle_message(user, channel, message)
            brain.handle_non_response()
        both of which return a list of tuples in one of the following forms:
            ( channel, message )
            ( channel, message, False )
            ( user, message, True )
        which will send those messages to those channels or users.

        name is used to differentiate log files, ideally this should match with
        the bot's name but it's not mandatory.
        '''

        self.name = name
        self.token = token
        formatter = logging.Formatter('%(asctime)s - %(message)s')
        self.error_logger = logging.getLogger('error_logger')
        error_hdlr = logging.FileHandler('logs/error_log_%s.log' % name)
        error_hdlr.setFormatter(formatter)
        self.error_logger.addHandler(error_hdlr)
        self.queued_messages = []
        self.last_message_time = time.time()-1

        if log_text:
            self.text_logger = logging.getLogger('text_logger')
            text_hdlr = logging.FileHandler('logs/slack_%s.log' % name)
            error_hdlr.setFormatter(formatter)
            self.text_logger.addHandler(text_hdlr)
        else:
            self.text_logger = False

        self.brain = brain

    def brain_implements(self, method_name):
        method = getattr(self.brain, method_name, None)
        return callable(method)

    def run(self):
        '''
        Call this to make the bot go live. Connects to slack and starts the
        main loop.
        '''
        key_okay = False
        while True:
            self.sc = slackclient.SlackClient(self.token)
            if not self.sc.rtm_connect():
                errmsg = 'Couldn\'t establish a connection! '
                if not key_okay:
                    print(errmsg + 'Check your client key?')
                    exit()
                else:
                    print(errmsg + 'Trying again in 10 seconds...')
                    time.sleep(10)
                    del self.sc
                    continue
            key_okay = True
            self.initialize()
            while True:
                try:
                    self.main_loop_handler()
                    time.sleep(0.1)
                except (socket.error, websocket._exceptions.WebSocketConnectionClosedException, slackclient.server.SlackConnectionError) as e:
                    print(e)
                    print('Lost connection, trying to reconnect in 10 seconds...')
                    time.sleep(10)
                    del self.sc
                    break

    def log_error(self, message='', dm=True):
        '''
        Sends the traceback of errors to ocharles on slack, and also logs the
        error locally. Call it like:
            try:
                <code>
            except:
                self.log_error()
        '''
        errorstring = traceback.format_exc()
        print(errorstring)
        if dm:
            self.send_dm('ocharles', u'%s\n```%s```' % (message,errorstring))
        self.error_logger.error(errorstring)

    def user_to_dm_channel(self, user):
        '''
        Tries to figure out the channel ID of the dm channel for user.
        '''
        #print user
        if user in self.user2id:
            user = self.user2id[user]
        j = self.sc.api_call('im.open', user=user)
        if 'channel' in j:
            return j['channel']['id']
        else:
            raise ValueError('Couldn\'t find a channel for user %s, json %s' % (
                user, json.dumps(j)))

    def send_dm(self, user, message):
        '''
        Tries to send a dm to user. For some reason this doesn't work when
        starting a new dm with someone.
        '''
        if user in self.user2id.keys():
            user = self.user2id[user]
        try:
            channel = self.user_to_dm_channel(user)
            self.sc.rtm_send_message(channel, message)
            return True
        except:
            self.log_error(dm=False)
            return False

    def initialize(self):
        '''
        Creates dictionaries mapping between user ids (e.g. U01234) and
        usernames (e.g. ghyun), and likewise for channels.
        '''
        self.id2channel = {x.id:x.name for x in self.sc.server.channels}
        self.channel2id = {x.name:x.id for x in self.sc.server.channels}
        
        self.id2user = make_uid2name(self.sc.api_call('users.list'))
        self.user2id = {self.id2user[x]:x for x in self.id2user}
        
        if self.brain_implements('startup_message'):
            self.send_messages(
                    self._filter_replies(self.brain.startup_message()))

        '''
        sent_dm = self.send_dm('ghyun', 'Initializing %s' % self.name)
        if not sent_dm:
            for user in self.user2id:
                self.send_dm(user, 'testing')
            exit('Tried to open DMs with everyone, please restart the bot now')
        '''

    def send_messages(self, messages_to_add):
        '''
        Manages the internal message queue, adding messages_to_add to the queue
        and sending things out at a speed that won't get the bot kicked from
        the server.
        '''
        self.queued_messages += messages_to_add
        now = time.time()
        if now  - self.last_message_time >= 1:
            self.queued_messages = util.compress_messages(self.queued_messages)
            if self.queued_messages:
                for channel, message in self.queued_messages:
                    try:
                        self.sc.rtm_send_message(channel, message)
                    except:
                        self.log_error()
                self.last_message_time = now
                self.queued_messages = []


    def _filter_replies(self, replies):
        '''
        brain.handle_message and brain_handle_non_response should return a
        list of "replies" in the form specified in the docstring for the init
        function of this class. If I get something else, that means the brain
        probably has a bug, so the bot will print this to the terminal.
        '''
        out = []
        for r in replies:
            if len(r) == 2:
                channel, message = r
                if channel and message:
                    out.append( ( channel, message) )
            elif len(r) == 3:
                channel, message, dmflag = r
                if dmflag:
                    try:
                        channel = self.user_to_dm_channel(channel)
                    except:
                        self.log_error()
                        continue
                out.append((channel, message))
            else:
                #self.send_dm('ghyun',  str(r) + ' is a wacky response yo!')
                print('Bad response received from brain:\n\t%s' % str(r))
        return out

    def main_loop_handler(self):
        '''
        Does stuff in the main loop. self.sc.rtm_read() returns a list of
        responses received since the last time it was called.
        '''
        messages_to_send = []
        for r in self.sc.rtm_read():
	    #print r
            if 'type' not in r or r['type'] != 'message':
                continue
            if response_is_message(r):
                messages_to_send += self._filter_replies(self.response_handler(r))
        messages_to_send += self._filter_replies(self.non_response_handler())
        self.send_messages(messages_to_send)

    def _replace_userid_with_name(self, word):
        '''
        When you @ someone on slack, I think you get something like <@U01234>
        instead of their name, so this is supposed to change that into their
        username.
        '''
        if len(word) > 1:
            if word[0] == '<' and word[-1] == '>' and word[1] == '@':
                newword = word.strip('<>@')
                if newword in self.id2user.keys():
                    return self.id2user[newword]
        return word

    def _message_preprocessor(self, message):
        '''
        Changes some things that slack formats funny into plaintext.
        '''
        out = []
        lines = message.split('\n')
        for line in lines:
            ms = line.split()
            #ms = map(self._replace_userid_with_name, ms)
            out.append(' '.join(ms))
        return '\n'.join(out)

    def response_handler(self, r):
        '''
        Does some preprocessing on the response sent by slack, and calls the
        brain on it.
        '''
        user = self.id2user.setdefault(r['user'], r['user'])
        channel = self.id2channel.setdefault(r['channel'], r['channel'])
        message = self._message_preprocessor(r['text'])
        if self.text_logger:
            self.text_logger.error(u'#%s | %s: %s' % (channel, user, message))
        if self.brain_implements('handle_message'):
            return self.brain.handle_message(user, channel, message)
        else:
            return []

    def non_response_handler(self):
        if self.brain_implements('handle_non_response'):
            return self.brain.handle_non_response()
        else:
            return []

        
