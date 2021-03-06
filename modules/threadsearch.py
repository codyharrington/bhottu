"""
Searches posts on 4chan using the 4chan JSON API and returns the post
url of any matching post

:author Cody Harrington:
"""
import re
import math
import json
import time
import requests
from api import *
from utils.pastebins import sprunge
from time import sleep
from threading import *
from collections import deque

def load():
    """Load the module"""
    registerFunction("catalog %s %S", search_catalog, "catalog <board> <regex>")
    registerFunction("board %s %S", search_board, "board <board> <regex>")
registerModule("ThreadSearch", load)

def sanitise(string):
    """Strips a string of all non-alphanumeric characters"""
    return re.sub(r"[^a-zA-Z0-9 ]", "", string)

def process_results(channel, sender, board, string, results_deque):
    """Process the resulting data of a search and present it"""
    max_num_urls_displayed = 3
    board = sanitise(board)
    message = ""
    if len(results_deque) <= 0:
        sendMessage(channel, "{0}: No results for {1}".format(sender, string))
    else:
        post_template = "https://boards.4chan.org/{0}/res/{1}"
        urls = [post_template.format(board, post_num) for post_num in results_deque]
        if len(urls) > max_num_urls_displayed:
            message = sprunge('\n'.join(urls))
        else:
            message = " ".join(urls[:max_num_urls_displayed])
        sendMessage(channel, "{0}: {1}".format(sender, message))

def get_json_data(url, sleep_time=0):
    """Returns a json data object from a given url."""
    # Respect 4chan's rule of at most 1 JSON request per second
    sleep(sleep_time)
    try:
        response = requests.get(url)
        if response.status_code == 404:
            log.error("url {} 404".format(url))
            return None
        json_data = json.loads(response.text.encode())
        return json_data
    except Exception as e:
        log.error("url: {}".format(url))
        log.error(e)
        raise

def search_thread(results_deque, thread_num, search_specifics):
    """
    Searches every post in thread thread_num on board board for the
    string provided. Returns a list of matching post numbers.
    """
    json_url = "https://a.4cdn.org/{0}/res/{1}.json".format(search_specifics["board"], thread_num)
    thread_json = get_json_data(json_url)

    if thread_json is not None:
        re_search = None
        for post in thread_json["posts"]:
            user_text = "".join([post[s] for s in search_specifics["sections"] if s in post.keys()])
            re_search = re.search(search_specifics["string"], user_text, re.UNICODE + re.IGNORECASE)
            if re_search is not None:
                results_deque.append("{0}#p{1}".format(thread_num, post["no"]))

def search_page(results_deque, page, search_specifics):
    """Will be run by the threading module. Searches all the 
    4chan threads on a page and adds matching results to synchronised queue"""
    for thread in page['threads']:
        user_text = "".join([thread[s] for s in search_specifics["sections"] if s in thread.keys()])
        if re.search(search_specifics["string"], user_text, re.UNICODE + re.IGNORECASE) is not None:
            results_deque.append(thread["no"])
        
def search_catalog(channel, sender, board, string):
    """Search all OP posts on the catalog of a board, and return matching results"""
    thread_join_timeout_seconds = 10
    results_deque = deque()
    json_url = "https://a.4cdn.org/{0}/catalog.json".format(board)
    sections = ["com", "name", "trip", "email", "sub", "filename"]
    catalog_json = get_json_data(json_url)
    search_specifics = {"sections" : sections, "board" : board, "string" : string}
    thread_pool = []

    for page in catalog_json:
        t = Thread(None, target=search_page, args=(results_deque, page, search_specifics))
        t.start()
        thread_pool.append(t)

    for _thread in thread_pool:
        if _thread.is_alive():
            _thread.join(float(thread_join_timeout_seconds))

    process_results(channel, sender, board, string, results_deque)

def search_board(channel, sender, board, string):
    """Search all the posts on a board and return matching results"""
    thread_join_timeout_seconds = 10
    results_deque = deque()
    json_url = "https://a.4cdn.org/{0}/threads.json".format(board)
    sections = ["com", "name", "trip", "email", "sub", "filename"]
    threads_json = get_json_data(json_url)
    search_specifics = {"sections" : sections, "board" : board, "string" : string}
    thread_pool = []

    for page in threads_json:
        for thread in page["threads"]:
            t = Thread(None, target=search_thread, args=(results_deque, thread["no"], search_specifics))
            t.start()
            thread_pool.append(t)
    
    for _thread in thread_pool:
        if _thread.is_alive():
            _thread.join(float(thread_join_timeout_seconds))

    process_results(channel, sender, board, string, results_deque)

