"""
Read urls of papers from swepapers database then scrape their abstracts and add data to the arxiv-sanity database.
"""

from sqlalchemy import create_engine
import requests
from bs4 import BeautifulSoup

def grab_papers():
    """Get a list of papers from swepapers database."""
    engine = create_engine('postgresql://postgres:postgres@localhost:5432/swepapers')
    with engine.connect() as connection:
        result = connection.execute("SELECT url FROM papers")
        papers = [row[0] for row in result]
    return papers

# def grab_venues():
#     """Get a list of venues from swepapers database."""
#     engine = create_engine('postgresql://postgres:postgres@localhost:5432/swepapers')
#     with engine.connect() as connection:
#         result = connection.execute("SELECT id, name FROM venues")
#         venues = {row[0]: row[1] for row in result}
#     return venues

# def map_id_to_venue(papers, venues):
#     """For each paper, replace its venue id with its name."""
#     for paper in papers:
#         paper['venue'] = venues[paper['venue']]
#     return papers

def map_dois_to_url(papers):
    """For each paper, replace its doi with its url."""
    for paper in papers:
        if type(paper["doi"]) is list:
            paper["url"] = paper["doi"][0]
        else:
            paper['url'] = paper['doi']
    return papers

def get_swe_paper_abstract(url):
    """Get the abstract of a paper from its url."""
    resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
    if resp.status_code != 200:
        print('Error: ' + resp.status_code)
        return ''
    soup = BeautifulSoup(resp.text, 'html.parser')
    if "acm.org" in resp.url:
        abstract = soup.find('div', {'class': 'abstractSection abstractInFull'})
        return abstract.text.lstrip().rstrip()
    elif "ieeexplore.ieee.org" in resp.url:
        abstract = soup.find('div', {'class': 'abstract-text'})
        return abstract.text
    return ''

def add_abstract(paper):
    """Add abstracts to the papers in the swepapers database."""
    abstract = get_swe_paper_abstract(paper['url'])
    paper['summary'] = abstract

def save_swepaper_to_arxiv_sanity(paper):
    """Save the papers from the swepapers database to the sqlite arxiv-sanity database"""
    engine = create_engine('sqlite:///data/papers.db')
    with engine.connect() as connection:
        connection.execute("INSERT INTO papers (key, value, venue_id) VALUES ('%s', '%s', '%s')" % (paper['key'], paper['value'], paper['venue_id']))

def main():
    """Main function."""
    papers = grab_papers()
    # venues = grab_venues()
    # papers = map_id_to_venue(papers, venues)
    papers = map_dois_to_url(papers)
    for paper in papers:
        paper = add_abstract(paper)
        paper["key"] = paper["url"]
        paper["value"] = paper
        save_swepaper_to_arxiv_sanity(paper)
    print(len(papers))

if __name__ == '__main__':
    main()
