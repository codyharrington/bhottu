"""
Searches posts on 4chan using the 4chan JSON API and returns the post
url of any matching post

:author Cody Harrington:
"""
import regex as re
import ujson as json
import time
import requests
import traceback
from api import *
from utils.pastebins import nnmm
from time import sleep
from threading import *
from collections import deque
from BeautifulSoup import BeautifulSoup
from xml.sax.saxutils import unescape
import time

total_time = 0

def load():
    """Load the module"""
    registerFunction("catalog %s %S", catalog_search_handler, "catalog <board> <regex>")
    registerFunction("board %s %S", board_search_handler, "board <board> <regex>")
registerModule("ThreadSearch", load)

def sanitise(string):
    """Strips a string of all non-alphanumeric characters"""
    return re.sub(r"[^a-zA-Z0-9 ]", "", string)

def catalog_search_handler(channel, sender, board, user_regex):
    """Handler for initiating catalog search"""
    results_data = perform_concurrent_4chan_search(board, user_regex, catalog_search=True)
    process_results(channel, sender, results_data)

def board_search_handler(channel, sender, board, user_regex):
    """Handler for initiating full board search"""
    results_data = perform_concurrent_4chan_search(board, user_regex, catalog_search=False)
    process_results(channel, sender, results_data)

def prettify_post(board, post_dict):
    """Takes a post dictionary, strips the <a> tags and replaces the <br> tags
    with newlines. It then appends a string of dashes '-' on the next line.
    """
    thread_num = post_dict["no"] if post_dict["resto"] == 0 else post_dict["resto"]
    post_link = "https://boards.4chan.org/%s/thread/%d#p%d" % (board, thread_num, post_dict["no"])
    comment = ""
    html_unescape_table = {
            "&#039;": "'",
            "&quot;": "\"",
            "&apos;": "'"
    }
    html_tag_replace_table = {
            "br": "\n",
            "wbr": "\r",
    }
    html_strip_tags = ["a", "b", "i", "u", "span"]

    if post_dict.has_key("com"):
        comment = BeautifulSoup(post_dict["com"]) 
        for (tag, replacement) in html_tag_replace_table.items():
            while getattr(comment, tag) != None:
                getattr(comment, tag).replaceWith(replacement)
        #while comment.wbr != None:
        #    comment.wbr.replaceWith("\r")
        for tag in html_strip_tags:
            while getattr(comment, tag) != None and getattr(getattr(comment, tag), "parent") != None:
                getattr(comment, tag).replaceWith(getattr(comment, tag).getText())
        #while comment.a != None and comment.a.parent != None:
        #    comment.a.replaceWith(comment.a.getText())
        #while comment.span != None:
        #    comment.span.replaceWith(comment.span.getText())

    comment = unescape(str(comment), html_unescape_table)

    return "%s\n\n%s" % (post_link, comment)

def process_results(channel, sender, results_data):
    """Process the resulting data of a search and present it"""
    global total_time

    search_parameters = results_data["search_parameters"]
    posts = results_data["posts"]

    if len(posts) <= 0:
        sendMessage(channel, "{0}: No results for {1} on {2}".format(sender, search_parameters["string"],
                                                                     search_parameters["user_board"]))
    else:
        message = nnmm('\n--------------------\n'.join([prettify_post(search_parameters["user_board"], post) for post in posts]))
        sendMessage(channel, "{0}: {1} | Search time {2:.2f}s | {3} matches".format(sender, message, total_time, len(posts)))

def get_json_data(url):
    """Returns a json data object from a given url."""
    response = None
    try:
        response = requests.get(url)
        if response.status_code == 404:
            log.error("url {}: 404".format(url))
            return None
        json_data = json.loads(response.text.encode())
        return json_data
    except Exception as e:
        if response is None:
            exception_string = "url: {0}\n{1}".format(url, traceback.format_exc())
        else:
            exception_string = "url: {0} status_code: {1}\n{2}".format(
                    url, response.status_code, traceback.format_exc())
        log.error(exception_string)
        print(exception_string)
        raise

def search_thread(results_deque, thread_num, search_parameters):
    """
    Searches every post in thread thread_num on a board for the
    string provided. Returns a list of matching post numbers.
    """
    json_url = "https://a.4cdn.org/%s/thread/%s.json" % (search_parameters["board"], thread_num)
    thread_json = get_json_data(json_url)
    if thread_json is None:
        return

    regex_search = search_parameters["compiled_regex"].search
    sections = search_parameters["sections"]
    deque_append = results_deque.append
    for post in thread_json["posts"]:
        for item in map(post.__getitem__, filter(post.has_key, sections)):
            if regex_search(item):
                deque_append(post)
                break


def search_catalog_page(results_deque, page, search_parameters):
    """Will be run by the threading module. Searches all the 
    4chan threads on a page and adds matching results to synchronised queue"""
    regex_search = search_parameters["compiled_regex"].search
    sections = search_parameters["sections"]
    deque_append = results_deque.append
    for thread in page["threads"]:
        for item in map(thread.__getitem__, filter(thread.has_key, sections)):
            if regex_search(item):
                deque_append(thread)
                break

def perform_concurrent_4chan_search(board, user_regex, catalog_search=False):
    """Search a thread or catalog on 4chan using several threads concurrently, then return relevant data"""
    global total_time
    thread_join_timeout_seconds = 10
    results_deque = deque()
    json_url = "https://a.4cdn.org/{0}/{1}.json".format(board, "catalog" if catalog_search else "threads")
    sections = ["com", "name", "filename", "sub", "ext", "country_name"]
    json_data = get_json_data(json_url)
    search_regex = re.compile(user_regex, re.UNICODE + re.IGNORECASE)
    search_parameters = {"sections": sections, "board": sanitise(board), "string": user_regex,
            "compiled_regex": search_regex, "user_board": board}
    results_data = {"posts": results_deque, "search_parameters": search_parameters}
    thread_pool = []

    start = time.time()

    if json_data is None:
        return results_data

    for page in json_data:
        if catalog_search:
            t = Thread(None, target=search_catalog_page, args=(results_deque, page, search_parameters))
            t.start()
            thread_pool.append(t)
        else:
            for thread in page["threads"]:
                t = Thread(None, target=search_thread, args=(results_deque, thread["no"], search_parameters))
                t.start()
                thread_pool.append(t)

    for _thread in thread_pool:
        if _thread.is_alive():
            _thread.join(float(thread_join_timeout_seconds))
    end = time.time()
    total_time = end - start
    return results_data


