"""
Flask server backend

ideas:
- allow delete of tags
- unify all different pages into single search filter sort interface
- special single-image search just for paper similarity
"""

import os
import re
import time
from random import shuffle

import numpy as np
from sklearn import svm

from flask import Flask, request, redirect, url_for
from flask import render_template
from flask import g # global session-level object
from flask import session

from aslite.db import get_papers_db, get_metas_db, get_tags_db, get_last_active_db, get_email_db
from aslite.db import load_features

# -----------------------------------------------------------------------------
# inits and globals

RET_NUM = 25 # number of papers to return per page

app = Flask(__name__)

# set the secret key so we can cryptographically sign cookies and maintain sessions
if os.path.isfile('secret_key.txt'):
    print("Secret key is available")
    # example of generating a good key on your system is:
    # import secrets; secrets.token_urlsafe(16)
    sk = open('secret_key.txt').read().strip()
else:
    print("WARNING: no secret key found, using default devkey")
    sk = 'devkey'
app.secret_key = sk

# -----------------------------------------------------------------------------
# globals that manage the (lazy) loading of various state for a request

def get_papers():
    if not hasattr(g, '_pdb'):
        g._pdb = get_papers_db()
    return g._pdb

def get_metas():
    if not hasattr(g, '_mdb'):
        g._mdb = get_metas_db()
    return g._mdb

@app.before_request
def before_request():
    g.user = session.get('user', None)

    # record activity on this user so we can reserve periodic
    # recommendations heavy compute only for active users
    if g.user:
        with get_last_active_db(flag='c') as last_active_db:
            last_active_db[g.user] = int(time.time())

@app.teardown_request
def close_connection(error=None):
    # close any opened database connections
    if hasattr(g, '_pdb'):
        g._pdb.close()
    if hasattr(g, '_mdb'):
        g._mdb.close()

# -----------------------------------------------------------------------------
# ranking utilities for completing the search/rank/filter requests

def render_pid(pid):
    # render a single paper with just the information we need for the UI
    pdb = get_papers()
#    tags = get_tags()
    thumb_path = 'static/thumb/' + pid + '.jpg'
    thumb_url = thumb_path if os.path.isfile(thumb_path) else ''
    d = pdb[pid]

    try:
        if d['authors']:
            authors = ', '.join(a['name'] if type(a) == dict else a for a in d['authors']),

        else:
            authors = ''

    except:
        authors = ''

    return dict(
        weight = 0.0,
        id = d['_id'],
        title = d['title'],
        authors = authors,
        time = d['_time_str'] if '_time_str' in d else str(d['_time']),
        tags="",
        utags=[],
        summary = d['summary'],
        thumb_url = thumb_url,
    )

def random_rank():
    mdb = get_metas()
    pids = list(mdb.keys())
    shuffle(pids)
    scores = [0 for _ in pids]
    return pids, scores

def time_rank():
    mdb = get_metas()
    ms = sorted(mdb.items(), key=lambda kv: kv[1]['_time'], reverse=True)
    tnow = time.time()
    pids = [k for k, v in ms]
    scores = [(tnow - v['_time'])/60/60/24 for k, v in ms] # time delta in days
    return pids, scores

def search_rank(q: str = ''):
    if not q:
        return [], []  # no query? no results

    # sanitize the query using a regex to remove any non-alphanumeric characters
    sanitized_query = sanitize_query(q)

    query_split = sanitized_query.lower().strip().split() # make lowercase then split query by spaces

    pdb = get_papers()

    match = lambda s: sum(min(3, s.lower().count(qp)) for qp in query_split)
    matchu = lambda s: sum(int(s.lower().count(qp) > 0) for qp in query_split)
    pairs = []
    for pid, p in pdb.items():
        score = 0.0
        score += 10.0 * matchu(' '.join([a['name'] if type(a) is dict else a for a in p['authors']])) if p['authors'] else 0.0
        score += 20.0 * matchu(p['title']) if p['title'] else 0.0
        score += 1.0 * match(p['summary'])
        if score > 0:
            pairs.append((score, pid))

    pairs.sort(reverse=True)
    pids = [p[1] for p in pairs]
    scores = [p[0] for p in pairs]
    return pids, scores


# helper function
def sanitize_query(query):
    """Sanitizes a query by allowing hyphens for author names and removing other non-alphanumeric characters."""

    # Regex Pattern Explanation:
    # [^a-zA-Z0-9 -]+: Matches any sequence of one or more characters that are NOT:
    #   * a-z: lowercase letters
    #   * A-Z: uppercase letters
    #   * 0-9: digits
    #   *  : space
    #   * -: hyphen
    #   * :: colon
    #   * ': apostrophe
    #   * ": quotation mark

    sanitized_query = re.sub(r'[^a-zA-Z0-9 -:\'\"]+', '', query) 
    return sanitized_query

# -----------------------------------------------------------------------------
# primary application endpoints

def default_context():
    # any global context across all pages, e.g. related to the current user
    context = {}
    context['user'] = g.user if g.user is not None else ''
    return context

@app.route('/', methods=['GET'])
def main():

    # default settings
    default_rank = 'time'
    # default_tags = ''
    default_time_filter = ''
    # default_skip_have = 'no'

    # override variables with any provided options via the interface
    opt_rank = request.args.get('rank', default_rank) # rank type. search|tags|pid|time|random
    opt_q = request.args.get('q', '') # search request in the text box
    opt_time_filter = request.args.get('time_filter', default_time_filter) # number of days to filter by
    opt_page_number = request.args.get('page_number', '1') # page number for pagination

    # only allow valid opt_ranks and default to time
    if opt_rank not in ["search", "time", "random"]:
        opt_rank = 'time'

    # if a query is given, override rank to be of type "search"
    # this allows the user to simply hit ENTER in the search field and have the correct thing happen
    if opt_q:
        opt_rank = 'search'

    # rank papers: by tags, by time, by random
    words = [] # only populated in the case of svm rank
    if opt_rank == 'search':
        pids, scores = search_rank(q=opt_q)
    elif opt_rank == 'time':
        pids, scores = time_rank()
    elif opt_rank == 'random':
        pids, scores = random_rank()
    else:
        raise ValueError("opt_rank %s is not a thing" % (opt_rank, ))

    # filter by time
    if opt_time_filter:
        mdb = get_metas()
        kv = {k:v for k,v in mdb.items()} # read all of metas to memory at once, for efficiency
        tnow = time.time()

        try:
            int_opt_time_filter = int(opt_time_filter)

        except ValueError:

            try:
                int_opt_time_filter = int(round(opt_time_filter))

            except TypeError:
                int_opt_time_filter = 20000  # should cover all results if invalid arg supplied

        deltat = int_opt_time_filter*60*60*24 # allowed time delta in seconds
        keep = [i for i,pid in enumerate(pids) if (tnow - kv[pid]['_time']) < deltat]
        pids, scores = [pids[i] for i in keep], [scores[i] for i in keep]

    # crop the number of results to RET_NUM, and paginate
    try:
        page_number = max(1, int(opt_page_number))
    except ValueError:
        page_number = 1

    start_index = (page_number - 1) * RET_NUM # desired starting index
    end_index = min(start_index + RET_NUM, len(pids)) # desired ending index
    pids = pids[start_index:end_index]
    scores = scores[start_index:end_index]

    # render all papers to just the information we need for the UI
    papers = [render_pid(pid) for pid in pids]
    for i, p in enumerate(papers):
        p['weight'] = float(scores[i])

    # build the page context information and render
    context = default_context()
    context['papers'] = papers
    # context['tags'] = rtags
    context['words'] = words
    context['words_desc'] = "Here are the top 40 most positive and bottom 20 most negative weights of the SVM. If they don't look great then try tuning the regularization strength hyperparameter of the SVM, svm_c, above. Lower C is higher regularization."
    context['gvars'] = {}
    context['gvars']['rank'] = opt_rank
    context['gvars']['time_filter'] = opt_time_filter
    context['gvars']['search_query'] = opt_q
    context['gvars']['page_number'] = str(page_number)
    return render_template('index.html', **context)

@app.route('/stats')
def stats():
    context = default_context()
    mdb = get_metas()
    kv = {k:v for k,v in mdb.items()} # read all of metas to memory at once, for efficiency
    times = [v['_time'] for v in kv.values()]
    tstr = lambda t: time.strftime('%b %d %Y', time.localtime(t))

    context['num_papers'] = len(kv)
    if len(kv) > 0:
        context['earliest_paper'] = tstr(min(times))
        context['latest_paper'] = tstr(max(times))
    else:
        context['earliest_paper'] = 'N/A'
        context['latest_paper'] = 'N/A'

    # count number of papers from various time deltas to now
    tnow = time.time()
    for thr in [1, 6, 12, 24, 48, 72, 96]:
        context['thr_%d' % thr] = len([t for t in times if t > tnow - thr*60*60])

    return render_template('stats.html', **context)

@app.route('/about')
def about():
    context = default_context()
    return render_template('about.html', **context)
