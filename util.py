import pytz
import ujson as json
import csv
import string
from slackclient import SlackClient
import unicodedata, re
import datetime

all_chars = (chr(i) for i in range(0x110000))
control_chars = ''.join(map(chr, list(range(0,32)) + list(range(127,160))))
control_char_re = re.compile('[%s]' % re.escape(control_chars))

def grammarify(l):
    '''
    Takes a list of strings, e.g. ['Alice', 'Bob', 'Joe'], and makes them into
    a grammatically-correct comma-separated list, i.e. "Alice, Bob, and Joe",
    or "Alice and Bob" if there were only 2.
    '''
    if len(l) == 0:
        return ''
    elif len(l) == 1:
        return l[0]
    elif len(l) == 2:
        return u'%s and %s' % (l[0], l[1])
    else:
        retstring = u''
        for item in l[:-1]:
            retstring += item + u', '
        retstring += u'and %s' % l[-1]
        return retstring

def remove_control_chars(s):
    return control_char_re.sub('', s)

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

def cleanstring(s):
    return remove_control_chars(' '.join(s.split()).strip().lower())

def utc_to_local(utc_dt):
    local_tz = pytz.timezone('US/Eastern')
    local_dt = utc_dt.replace(tzinfo=pytz.utc).astimezone(local_tz)
    return local_tz.normalize(local_dt)

def is_sublist(sublst, lst):
    n = len(sublst)
    return any((sublst == lst[i:i+n]) for i in range(len(lst)-n+1))

def read_resource_dict():
    # Resource dictionary
    base_fn = 'locus_data/Resource Dictionary (Live) - '
    fns = [base_fn + ending for ending in ['A.csv', 'B.csv', 'C.csv', 'D.csv', 'E.csv']]
    r_dict = {}
    for fn in fns:
        with open(fn, 'rb') as f:
            reader = csv.reader(f)
            reader.next()
            for row in reader:
                name = row[0]
                locus = '%s %s %s' % (row[1], row[2], row[3])
                if name not in r_dict.keys():
                    r_dict[name] = {'answer': locus}
                else:
                    print(name, locus, r_dict[name])
                    exit()
    return r_dict

def read_analyst_dict():
    # Analyst dictionary
    ad = {}
    with open('locus_data/Analyst Dictionary.csv','rb') as f:
        reader = csv.reader(f)
        reader.next()
        for row in reader:
            adid = str(row[0])
            title = row[1]
            desc = row[2]
            el = row[11].strip()
            key = '%s: %s' % (title, desc)
            ad[key] = {'answer':el
                    , 'adid': adid}
    return ad

def read_analyst_dict_1():
    # Analyst dictionary
    ad = {}
    with open('locus_data/Analyst Dictionary.csv','rb') as f:
        reader = csv.reader(f)
        reader.next()
        for row in reader:
            adid = str(row[0])
            title = row[1]
            desc = row[2]
            el = row[11].strip()
            ad[adid] = {'title': title
                    , 'el': el
                    }
    return ad

def create_id2user(api_call):
    users = api_call['members']
    out = {}
    for u in users:
        out[u['id']] = u['name']
    return out

def create_id2channel(channels):
    out = {}
    for c in channels:
        out[c.id] = c.name
    return out

def reverse_dict(d):
    return {d[k]:k for k in d}

def compress_messages(messages):
    '''
    Looks through a list of messages, i.e. (channel, message) tuples, and if
    many messages are being sent to the same channel, it compresses them into
    one message, separated by newline characters.
    '''
    out = []
    for channel, message in messages:
        if not out:
            out.append( [channel, message] )
        elif out[-1][0] == channel:
            out[-1][1] += '\n' + message
        else:
            out.append( [channel, message] )
    return out

def load_json(fn):
    '''
    I don't know what possessed me to write this
    '''
    with open(fn, 'rb') as f:
        return json.load(f)
def dump_json(obj, fn):
    with open(fn, 'wb') as f:
        json.dump(obj, f)
def update_dict(d, deltas, fn='', dump=True):
    for k,v in deltas.iteritems():
        dict_pe(d, k, v)
    if dump:
        dump_json(d, fn)

def dict_pe(d, k, delta):
    ''' Stands for "dict +=" lmao '''
    d[k] = d.setdefault(k, 0) + delta

def subdict_pe(d, k1, k2, delta):
    ''' used in userstats '''
    d[k1][k2] = d.setdefault(k1, {}).setdefault(k2,0) + delta

def seconds_to_timestring(s):
    return str(datetime.timedelta(seconds=s)).split('.')[0]

def print_nice_table(l1, l2):
    '''
    Takes two lists, e.g. a list of users and a list of their scores, and
    returns a nice table where the values from the first list are left-aligned
    and the values of the second list are right-aligned.
    '''
    assert len(l1) == len(l2)
    if not l1:
        return ''
    l1 = map(str, l1)
    l2 = map(str, l2)
    maxl1 = max([len(x) for x in l1])
    maxl2 = max([len(x) for x in l2])
    out = [ l1[i].ljust(maxl1+1) + l2[i].rjust(maxl2) for i in range(len(l1))]
    return '\n'.join(out)

def ascii_progress_bar(progress, total, length=10):
    '''
    Shows a progress bar like
        [=====     ]
    where length is the total number of equals signs between the endpoints,
    i.e. the total length of the bar is length+2
    '''
    nequals = int(round(float(progress)/total * length))
    nspaces = length - nequals
    return '[%s%s]' % ('='*nequals, ' '*nspaces)

def bold_substring_in_sentence(substring, sentence):
    '''
    Takes a substring in a sentence, and wraps it in ` symbols to make them
    into redtext on slack.
    '''
    '''
    start_index = sentence.lower().index(substring.lower())
    end_index = start_index + len(substring)
    return sentence[:start_index] + '`' + sentence[start_index:end_index] + '`' + sentence[end_index:]
    '''
    s_sentence = sentence.split()
    s_substring = substring.split()
    start_index = [i for i in range(len(s_sentence) - len(s_substring) + 1) for j in range(len(s_substring)) if s_sentence[i+j] == s_substring[j] ][0]
    end_index = start_index + len(s_substring) - 1
    s_sentence[start_index] = '`%s' % s_sentence[start_index]
    s_sentence[end_index] = '%s`' % s_sentence[end_index]
    return ' '.join(s_sentence)

def bold_valid_substring_in_sentence(substring, sentence):
    '''
    Takes a phrase and a sentence in the form
    [parse_tree, [(firstwordindex, phrase), ...]]
    and highlights the phrase if it appears in the list of valid phrases
    '''
    parse, phrases = sentence
    s_sentence = sentence[0].split()
    s_substring = substring.split()
    start_index = [x[0] for x in phrases if x[1].strip().lower() == substring.strip().lower()][0]-len(s_substring)
    end_index = start_index + len(s_substring)-1
    s_sentence[start_index] = '`%s' % s_sentence[start_index]
    s_sentence[end_index] = '%s`' % s_sentence[end_index]
    return ' '.join(s_sentence)
