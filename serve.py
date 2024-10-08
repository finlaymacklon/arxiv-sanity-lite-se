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

def svm_rank(pid: str = '', C: float = 0.01):

    # tag can be one tag or a few comma-separated tags or 'all' for all tags we have in db
    # pid can be a specific paper id to set as positive for a kind of nearest neighbor search
    if pid is None or pid == '':
        return [], [], []

    # load all of the features
    features = load_features()
    x, pids = features['x'], features['pids']
    n, d = x.shape
    ptoi, itop = {}, {}
    for i, p in enumerate(pids):
        ptoi[p] = i
        itop[i] = p

    if pid not in ptoi:
        # this paper ID does not exist in our index
        return [], [], []

    # construct the positive set
    y = np.zeros(n, dtype=np.float32)
    y[ptoi[pid]] = 1.0

    if y.sum() == 0:
        return [], [], []  # there are no positives?

    # classify
    clf = svm.LinearSVC(class_weight='balanced', verbose=False, max_iter=10000, tol=1e-6, C=C)
    clf.fit(x, y)
    s = clf.decision_function(x)
    sortix = np.argsort(-s)
    pids = [itop[ix] for ix in sortix]
    scores = [100 * float(s[ix]) for ix in sortix]

    # get the words that score most positively and most negatively for the svm
    ivocab = {v:k for k,v in features['vocab'].items()} # index to word mapping
    weights = clf.coef_[0] # (n_features,) weights of the trained svm
    sortix = np.argsort(-weights)
    words = []
    for ix in list(sortix[:40]) + list(sortix[-20:]):
        words.append({
            'word': ivocab[ix],
            'weight': weights[ix],
        })
    return pids, scores, words


def search_rank(q: str = ''):
    if (q is None) or (q == ""):
        return [], []  # no query? no results

    # sanitize the query using a regex to remove any non-alphanumeric characters
    sanitized_query = sanitize_string(q)

    query_split = sanitized_query.lower().strip().split()  # make lowercase then split query by spaces

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
def sanitize_string(string):
    """Only include alphanumeric characters (and some special chars) for the search query or DOI"""

    # Regex Pattern Explanation:
    # [^a-zA-Z0-9 -]+: Matches any sequence of one or more characters that are NOT:
    #   * a-z: lowercase letters
    #   * A-Z: uppercase letters
    #   * 0-9: digits
    #   *  : space
    #   * -: hyphen
    #   * :: colon
    #   * ': apostrophe
    #   * ?: question mark
    #   * !: exclamation point
    #   * .: decimal point / period / full-stop
    #   * /: forward slash

    string_sanitized = re.sub(r'[^a-zA-Z0-9 -:\'\".?!\/]]+', '', string) 
    return string_sanitized

# -----------------------------------------------------------------------------
# primary application endpoints

def default_context():
    # any global context across all pages, e.g. related to the current user
    context = {}
    # context['user'] = g.user if g.user is not None else ''
    return context

@app.route('/', methods=['GET'])
def main():

    # default settings
    default_rank = 'time'
    default_time_filter = ''

    # override variables with any provided options via the interface
    opt_rank = request.args.get('rank', default_rank) # rank type. search|tags|pid|time|random
    opt_q = request.args.get('q', '') # search request in the text box
    opt_pid = request.args.get('pid', '')  # pid to find nearest neighbors to
    opt_time_filter = request.args.get('time_filter', default_time_filter) # number of days to filter by
    opt_svm_c = request.args.get('svm_c', '') # svm C parameter
    opt_page_number = request.args.get('page_number', '1') # page number for pagination

    # only allow valid opt_ranks and default to time
    if opt_rank not in ["search", "pid", "time", "random"]:
        opt_rank = default_rank

    # if a query is given, override rank to be of type "search"
    # this allows the user to simply hit ENTER in the search field and have the correct thing happen
    if (opt_q is not None) and (opt_q != ""):
        opt_rank = 'search'

    # try to parse opt_svm_c into something sensible (a float)
    try:
        C = float(opt_svm_c)

    except ValueError:
        C = 0.01  # sensible default, i think

    # clean up the pid parameter
    if (opt_pid is not None) and (opt_pid != ""):
        opt_pid = sanitize_string(opt_pid)

    # rank papers: by tags, by time, by random
    words = []  # only populated in the case of svm rank
    if opt_rank == 'search':
        pids, scores = search_rank(q=opt_q)

    elif opt_rank == 'pid':
        pids, scores, words = svm_rank(pid=opt_pid, C=C)

    elif opt_rank == 'time':
        pids, scores = time_rank()

    elif opt_rank == 'random':
        pids, scores = random_rank()

    else:
        # raise ValueError("opt_rank %s is not a thing" % (opt_rank, ))
        # Invalid rank parameter passed, so render empty index
        return render_template('index.html', default_context())

    # filter by time
    if (opt_time_filter is not None) and (opt_time_filter != default_time_filter):
        mdb = get_metas()
        kv = {k: v for k, v in mdb.items()}  # read all of metas to memory at once, for efficiency
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

    # optionally hide papers we already have
    # if opt_skip_have == 'yes':
    #     tags = get_tags()
    #     have = set().union(*tags.values())
    #     keep = [i for i,pid in enumerate(pids) if pid not in have]
    #     pids, scores = [pids[i] for i in keep], [scores[i] for i in keep]

    # crop the number of results to RET_NUM, and paginate
    try:
        page_number = max(1, int(opt_page_number))
    except ValueError:
        page_number = 1

    start_index = (page_number - 1) * RET_NUM  # desired starting index
    end_index = min(start_index + RET_NUM, len(pids))  # desired ending index
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
    # context['gvars']['tags'] = opt_tags
    context['gvars']['pid'] = opt_pid
    context['gvars']['time_filter'] = opt_time_filter
    # context['gvars']['skip_have'] = opt_skip_have
    context['gvars']['search_query'] = opt_q
    context['gvars']['svm_c'] = str(C)
    context['gvars']['page_number'] = str(page_number)
    return render_template('index.html', **context)

@app.route('/inspect', methods=['GET'])
def inspect():

    # fetch the paper of interest based on the pid
    pid = request.args.get('pid', '')
    pdb = get_papers()
    if pid not in pdb:
        return "error, malformed pid" # todo: better error handling

    # load the tfidf vectors, the vocab, and the idf table
    features = load_features()
    x = features['x']
    idf = features['idf']
    ivocab = {v:k for k,v in features['vocab'].items()}
    pix = features['pids'].index(pid)
    wixs = np.flatnonzero(np.asarray(x[pix].todense()))
    words = []
    for ix in wixs:
        words.append({
            'word': ivocab[ix],
            'weight': float(x[pix, ix]),
            'idf': float(idf[ix]),
        })
    words.sort(key=lambda w: w['weight'], reverse=True)

    # package everything up and render
    paper = render_pid(pid)
    context = default_context()
    context['paper'] = paper
    context['words'] = words
    context['words_desc'] = "The following are the tokens and their (tfidf) weight in the paper vector. This is the actual summary that feeds into the SVM to power recommendations, so hopefully it is good and representative!"
    return render_template('inspect.html', **context)

#@app.route('/profile')
#def profile():
#    context = default_context()
#    with get_email_db() as edb:
#        email = edb.get(g.user, '')
#        context['email'] = email
#    return render_template('profile.html', **context)

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
