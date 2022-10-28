"""
Read urls of papers from swepapers database, then scrape their abstracts and add data to the arxiv-sanity database.
"""
import time
import logging 
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from sqlalchemy import create_engine
from aslite.db import get_papers_db, get_metas_db

def setup_logger(file_name, logger_name=None):

        if logger_name is None:
            logger_name = file_name

        path_logs = Path("./log")

        path_logs.mkdir(exist_ok=True, parents=True)

        logger = logging.getLogger(logger_name)
        logger.handlers.clear()

        log_file_name = f'{file_name}.log'
        log_file_path = path_logs / log_file_name

        log_format = logging.Formatter('%(name)s @ %(asctime)s [%(levelname)s] : %(message)s')

        file_handler = logging.FileHandler(log_file_path.as_posix(), mode='w')
        file_handler.setFormatter(log_format)

        logger.addHandler(file_handler)
        # logger.addHandler(logging.StreamHandler(sys.stdout))
        logger.setLevel(logging.INFO)

        return logger

def grab_papers():
    """Get a list of papers from swepapers database."""
    engine = create_engine('postgresql://postgres:postgres@localhost:5432/swepapers')
    with engine.connect() as connection:
        result = connection.execute("SELECT authors, title, ee, doi FROM papers")
        papers = [dict(row) for row in result]
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

def map_urls_to_link(papers):
    """For each paper, replace its doi with its url."""
    for paper in papers:
        if type(paper["ee"]) is list:
            paper["link"] = paper['ee'][0]
        else:
            paper['link'] = paper['ee']
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
        abstract = soup.find("meta", {"property": "og:description"})["content"]
        return abstract
    return ''

def add_abstract(paper):
    """Add abstracts to the papers in the swepapers database."""
    abstract = get_swe_paper_abstract(paper['link'])
    paper['summary'] = abstract
    paper["_time"] = time.time()
    return paper

def save_swepaper_to_arxiv_sanity(paper):
    """Save the papers from the swepapers database to the sqlite arxiv-sanity database"""
    required_keys = ['authors', 'title', 'summary', '_time', '_id']
    # engine = create_engine('sqlite:///data/papers.db')
    # with engine.connect() as connection:
    #     connection.execute("INSERT INTO papers (key, value) VALUES ('%s', '%s')" % (paper['doi'], { k: paper[k] for k in required_keys }))
    pdb = get_papers_db(flag='c')
    pdb[paper['doi']] = { k: paper[k] for k in required_keys }
    

def save_swepaper_time_to_arxiv_sanity(paper):
    """Save the papers from the swepapers database to the sqlite arxiv-sanity database"""
    # engine = create_engine('sqlite:///data/papers.db')
    # with engine.connect() as connection:
    #     connection.execute("INSERT INTO metas (key, value) VALUES ('%s', '%s')" % (paper['doi'], { '_time': paper['_time'] }))
    mdb = get_metas_db(flag='c')
    mdb[paper['doi']] = {'_time': paper['_time']}

def main():
    """Main function."""
    logger = setup_logger("add_published_papers")
    # print("Started.")
    papers = grab_papers()
    # venues = grab_venues()
    # papers = map_id_to_venue(papers, venues)
    papers = map_urls_to_link(papers)
    sleep_counter = 1
    for paper in papers:
        # print(f"Processing paper {paper['link']}", end=" ... ")
        try:
            paper["_id"] = paper["doi"]
            paper = add_abstract(paper)     
            save_swepaper_to_arxiv_sanity(paper)
            save_swepaper_time_to_arxiv_sanity(paper)
            # print("Done.")  
        except:
            # print("Failed")
            logger.error(f"Failed to process paper {paper['link']}")
        # rate limit
        if sleep_counter % 5 == 0:
            time.sleep(1)
        else:
            time.sleep(0.5)
        # show progress
        print(f"Progress: {sleep_counter}/{len(papers)}", end="\r")
        sleep_counter += 1

    print("Finished.")

if __name__ == '__main__':
    main()
