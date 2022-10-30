# TODO
Things to fix/add before it is reasonable to host a searchable, public, live version on the web.

## Bugs to fix
1) **sanitize inputs better - they should match current arxiv-sanity stuff**
- author names sometimes have numbers attached - I don't think we need this, if an author is named the same as someone else, they are probably distinguished by the area of their work, and if not, maybe instead it is a better idea to sanitize the author names when calculating the tf-idf features (remove numerical tokens)
- the author data needs to be a dictionary with ['name'] rather than a list of names
- replace missing titles "None" with empty string OR more likely, exclude from papers table in database (for now)
- create the field '_time_str' for each paper so that it can be used later on when displaying papers

2) **Fix the links so that non-arxiv papers link to their actual url instead of arxiv/abs/:doi**
- currently links are all to arxiv but not all papers are from arxiv

3) **Add tags for published papers**
- might just be a case of making each entry for published papers have an empty tags list, not sure

## Features to add
1) **add way to scrape the abstract for papers not on IEEE, ACM**
- many papers may be from sciencedirect (elsevier), or some other publishers
- at the moment we only have abstracts for papers published in IEEE, ACM
- this was because I was lazy

2) **have another database or table for missing papers or papers that do not have a title, authors, or abstract**
- some papers did not get added to the database, and some are just press releases etc.
- for real papers not in database, we should find new ways to scrape the required data so that the paper can be moved to our main table
- for example, with abstracts, maybe we can get them from google scholar or something like that - wouldn't trust my own OCR really..pain in the butt too

3) **add venues and publisher to the web interface, I also want to know if this paper is from arxiv or published through IEEE, ACM, etc.**
- the venue might also be relevant when calculating tf-idf features
- means we need to add a field to the papers table for venue and publisher; for arxiv papers the venue will be empty unless the paper is also published

4) **ensure papers are not duplicated between arxiv and published version in the papers table**
- we want the union of the arxiv and published version's data
- no duplicates allowed, based off of authors + title, or maybe DOI...but I think DOI is seperate for arxiv/published
- combine their data in the papers table
- we mainly want arxiv data but for the published version we want the venue and where it was published - optional secondary link to published version?
- prefer not to link to paywalled stuff if freely available version can be linked to instead

5) **add way to get newly published papers and add them to dataset**
- at the moment limited to papers in general-index dataset, which runs up to 2021ish (? double-check this, just from memory)
- easier to just take ones from arxiv but can't be sure that all will share their work freely on arxiv
- should have method to automatically check and update the database as papers are published, similarly to how Andrej Karpathy set up `arxiv_daemon.py` to run for `arxiv-sanity-lite`

## Repository structure
It probably makes sense to instantiate a new repository and use the `arxiv-sanity-lite` and `general-index-se` forks just as submodules to use their code. Not sure, but would provide more control over posting issues/receiving contributions if that ever becomes a need.

## Serve live version
Per Andrej Karpathy, `arxiv-sanity-lite` indexing ~30k papers can be run on the following plan from [Linode](https://www.linode.com/pricing/)

| Plan	      | $/Mo	| $/Hr	 | RAM 	 | CPUs	| Storage	| Transfer	| Network In/Out |	
| -           | -       |  -     | -     |  -   | -         | -         | -              |
| Nanode 1 GB |	$5	    |$0.0075 |	1 GB | 	1	|  25 GB	| 1 TB	    |40/1 Gbps       |