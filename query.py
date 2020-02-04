from __future__ import division

import json
import requests
import urllib
import random
import datetime as dt

from functools import partial
from billiard.pool import Pool
from bs4 import BeautifulSoup
from itertools import cycle
from numpy import *
from tweet import Tweet
import logging
import sys


HEADERS_LIST = [
    'Mozilla/5.0 (Windows; U; Windows NT 6.1; x64; fr; rv:1.9.2.13) Gecko/20101203 Firebird/3.6.13',
    'Mozilla/5.0 (compatible, MSIE 11, Windows NT 6.3; Trident/7.0; rv:11.0) like Gecko',
    'Mozilla/5.0 (Windows; U; Windows NT 6.1; rv:2.2) Gecko/20110201',
    'Opera/9.80 (X11; Linux i686; Ubuntu/14.10) Presto/2.12.388 Version/12.16',
    'Mozilla/5.0 (Windows NT 5.2; RW; rv:7.0a1) Gecko/20091211 SeaMonkey/9.23a1pre'
]

HEADER = {'User-Agent': random.choice(HEADERS_LIST)}

INIT_URL = 'https://twitter.com/search?f=tweets&vertical=default&q={q}&l={lang}'
RELOAD_URL = 'https://twitter.com/i/search/timeline?f=tweets&vertical=' \
             'default&include_available_features=1&include_entities=1&' \
             'reset_error_state=false&src=typd&max_position={pos}&q={q}&l={lang}'
INIT_URL_USER = 'https://twitter.com/{u}'
RELOAD_URL_USER = 'https://twitter.com/i/profiles/show/{u}/timeline/tweets?' \
                  'include_available_features=1&include_entities=1&' \
                  'max_position={pos}&reset_error_state=false'
PROXY_URL = 'https://free-proxy-list.net/'

def get_proxies():
    response = requests.get(PROXY_URL)
    soup = BeautifulSoup(response.text, 'lxml')
    table = soup.find('table',id='proxylisttable')
    list_tr = table.find_all('tr')
    list_td = [elem.find_all('td') for elem in list_tr]
    list_td = list(filter(None, list_td))
    list_ip = [elem[0].text for elem in list_td]
    list_ports = [elem[1].text for elem in list_td]
    list_proxies = [':'.join(elem) for elem in list(zip(list_ip, list_ports))]
    return list_proxies               
                  
def get_query_url(query, lang, pos, from_user = False):
    if from_user:
        if pos is None:
            return INIT_URL_USER.format(u=query)
        else:
            return RELOAD_URL_USER.format(u=query, pos=pos)
    if pos is None:
        return INIT_URL.format(q=query, lang=lang)
    else:
        return RELOAD_URL.format(q=query, pos=pos, lang=lang)

def linspace(start, stop, n):
    if n == 1:
        yield stop
        return
    h = (stop - start) / (n - 1)
    for i in range(n):
        yield start + h * i

proxies = get_proxies()
proxy_pool = cycle(proxies)

def query_single_page(query, lang, pos, retry=50, from_user=False, timeout=60):
    url = get_query_url(query, lang, pos, from_user)

    proxy = next(proxy_pool)
    response = requests.get(url, headers=HEADER, proxies={"http": proxy}, timeout=timeout)
    if pos is None:  # html response
        html = response.text or ''
        json_resp = None
    else:
        html = ''
        json_resp = response.json()
        html = json_resp['items_html'] or ''
    tweets = list(Tweet.from_html(html))

    if not tweets:
        if json_resp:
            pos = json_resp['min_position']
            has_more_items = json_resp['has_more_items']
            if not has_more_items:
                return [], None
        else:
            pos = None

        if retry > 0:
            return query_single_page(query, lang, pos, retry - 1, from_user)
        else:
            return [], pos

    if json_resp:
        return tweets, urllib.parse.quote(json_resp['min_position'])
    if from_user:
        return tweets, tweets[-1].tweet_id
    return tweets, "TWEET-{}-{}".format(tweets[-1].tweet_id, tweets[0].tweet_id)

    if retry > 0:
        return query_single_page(query, lang, pos, retry - 1)

    return [], None


def query_tweets_once_generator(query, limit=None, lang='', pos=None):
    query = query.replace(' ', '%20').replace('#', '%23').replace(':', '%3A').replace('&', '%26')
    num_tweets = 0
    while True:
        new_tweets, new_pos = query_single_page(query, lang, pos)
        if len(new_tweets) == 0:
            return

        for t in new_tweets:
            yield t, pos

        # use new_pos only once you have iterated through all old tweets
        pos = new_pos

        num_tweets += len(new_tweets)

        if limit and num_tweets >= limit:
            return

   
def query_tweets_once(*args, **kwargs):
    res = list(query_tweets_once_generator(*args, **kwargs))
    if res:
        tweets, positions = zip(*res)
        return tweets
    else:
        return []


def query_tweets(query, limit=None, begindate=dt.date(2006, 3, 21), enddate=dt.date.today(), poolsize=20, lang=''):
    no_days = (enddate - begindate).days
    
    if(no_days < 0):
        sys.exit('Begin date must occur before end date.')
    
    if poolsize > no_days:
        poolsize = no_days
    dateranges = [begindate + dt.timedelta(days=elem) for elem in linspace(0, no_days, poolsize+1)]

    if limit and poolsize:
        limit_per_pool = (limit // poolsize)+1
    else:
        limit_per_pool = None

    queries = ['{} since:{} until:{}'.format(query, since, until)
               for since, until in zip(dateranges[:-1], dateranges[1:])]

    all_tweets = []
    try:
        pool = Pool(poolsize)
        for new_tweets in pool.imap_unordered(partial(query_tweets_once, limit=limit_per_pool, lang=lang), queries):
            all_tweets.extend(new_tweets)
    finally:
        pool.close()
        pool.join()

    return all_tweets





