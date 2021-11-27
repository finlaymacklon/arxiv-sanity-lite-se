"""
Compose and send recommendation emails to arxiv-sanity-lite users!

I run this script in a cron job to send out emails to the users with their
recommendations. There's a bit of copy paste code here but I expect that
the recommendations may become more complex in the future, so this is ok for now.

You'll notice that the file sendgrid_api_key.txt is not in the repo, you'd have
to manually register with sendgrid yourself, get an API key and put it in the file.
"""

import os
import time
import numpy as np
from sklearn import svm

import sendgrid
from sendgrid.helpers.mail import Email, To, Content, Mail

from aslite.db import load_features
from aslite.db import get_tags_db
from aslite.db import get_metas_db
from aslite.db import get_papers_db
from aslite.db import get_email_db

# -----------------------------------------------------------------------------
# the html template for the email

template = """
<!DOCTYPE HTML>
<html>

<head>
<style>
body {
    font-family: Arial, sans-serif;
}
.s {
    font-weight: bold;
    margin-right: 10px;
}
.a {
    color: #333;
}
.u {
    font-size: 12px;
    color: #333;
    margin-bottom: 10px;
}
</style>
</head>

<body>

<br><br>
<div>Good morning! Here are your daily <a href="https://arxiv-sanity-lite.com">arxiv-sanity-lite</a> recommendations of very recent papers:</div>
<br><br>

<div>
    __CONTENT__
</div>

<br><br>
<div>
To stop these emails remove your email in your <a href="https://arxiv-sanity-lite.com/profile">account</a> settings.
</div>
<br><br>

</body>
</html>
"""

# -----------------------------------------------------------------------------

def calculate_recommendation(
    tags,
    time_delta = 3, # how recent papers are we recommending? in days
    ):

    # a bit of preprocessing
    x, pids = features['x'], features['pids']
    n, d = x.shape
    ptoi, itop = {}, {}
    for i, p in enumerate(pids):
        ptoi[p] = i
        itop[i] = p

    # construct the positive set via simple union of all tags
    y = np.zeros(n, dtype=np.float32)
    for tag, pids in tags.items():
        for pid in pids:
            y[ptoi[pid]] = 1.0

    # classify
    clf = svm.LinearSVC(class_weight='balanced', verbose=False, max_iter=10000, tol=1e-6, C=0.1)
    clf.fit(x, y)
    s = clf.decision_function(x)
    sortix = np.argsort(-s)
    pids = [itop[ix] for ix in sortix]
    scores = [100*float(s[ix]) for ix in sortix]

    # filter by time to only recent papers
    deltat = time_delta*60*60*24 # allowed time delta in seconds
    keep = [i for i,pid in enumerate(pids) if (tnow - metas[pid]['_time']) < deltat]
    pids, scores = [pids[i] for i in keep], [scores[i] for i in keep]

    # finally exclude the papers we already have tagged
    have = set().union(*tags.values())
    keep = [i for i,pid in enumerate(pids) if pid not in have]
    pids, scores = [pids[i] for i in keep], [scores[i] for i in keep]

    return pids, scores

# -----------------------------------------------------------------------------

def render_recommendations(pids, scores, num_recommendations = 10):
    # render the paper recommendations into the html template

    parts = []
    n = min(len(scores), num_recommendations)
    for score, pid in zip(scores[:n], pids[:n]):
        p = pdb[pid]
        authors = ', '.join(a['name'] for a in p['authors'])
        # crop the abstract
        summary = p['summary']
        summary = summary[:min(500, len(summary))]
        if len(summary) == 500:
            summary += '...'
        parts.append(
"""
<tr>
<td valign="top"><div class="s">%.2f</div></td>
<td>
<a href="%s">%s</a>
<div class="a">%s</div>
<div class="u">%s</div>
</td>
</tr>
""" % (score, p['link'], p['title'], authors, summary)
        )

    final = '<table>' + ''.join(parts) + '</table>'
    out = template.replace('__CONTENT__', final)
    return out

# -----------------------------------------------------------------------------
# send the actual html via sendgrid

def send_email(to, html):

    # init the api
    assert os.path.isfile('sendgrid_api_key.txt')
    api_key = open('sendgrid_api_key.txt', 'r').read().strip()
    sg = sendgrid.SendGridAPIClient(api_key=api_key)

    # construct the email
    from_email = Email("admin@arxiv-sanity-lite.com")
    to_email = To(to)
    subject = tnow_str + " Arxiv Sanity Lite recommendations"
    content = Content("text/html", html)
    mail = Mail(from_email, to_email, subject, content)

    # hope for the best :)
    response = sg.client.mail.send.post(request_body=mail.get())
    print(response.status_code)

# -----------------------------------------------------------------------------

if __name__ == "__main__":

    TIME_DELTA = 3 # how recent papers are we recommending? in days
    NUM_RECCOMENDATIONS = 20 # how many papers to recommend?

    tnow = time.time()
    tnow_str = time.strftime('%b %d', time.localtime(tnow)) # e.g. "Nov 27"

    # read entire db simply into RAM
    with get_tags_db() as tags_db:
        tags = {k:v for k,v in tags_db.items()}

    # read entire db simply into RAM
    with get_metas_db() as mdb:
        metas = {k:v for k,v in mdb.items()}

    # read entire db simply into RAM
    with get_email_db() as edb:
        emails = {k:v for k,v in edb.items()}

    # read tfidf features into RAM
    features = load_features()

    # keep the papers as only a handle, since this can be larger
    pdb = get_papers_db()

    # iterate all users, create recommendations, send emails
    for user, tags in tags.items():

        # verify that we have an email for this user
        email = emails.get(user, None)
        if not email:
            print("skipping user %s, no email" % (user, ))
            continue

        # calculate the recommendations
        pids, scores = calculate_recommendation(tags, time_delta=TIME_DELTA)
        print("user %s has %d recommendations over last %d days" % (user, len(pids), TIME_DELTA))
        if len(pids) == 0:
            print("skipping the rest, no recommendations were produced")
            continue

        # render the html
        print("rendering top %d recommendations into a report..." % (NUM_RECCOMENDATIONS, ))
        html = render_recommendations(pids, scores, num_recommendations=NUM_RECCOMENDATIONS)
        # temporarily for debugging write recommendations to disk for manual inspection
        if os.path.isdir('recco'):
            with open('recco/%s.html' % (user, ), 'w') as f:
                f.write(html)

        # actually send the email
        print("sending email...")
        send_email(email, html)


    print("done.")
