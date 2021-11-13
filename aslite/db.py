"""
Database support functions
"""

import sqlite3, zlib, pickle
from sqlitedict import SqliteDict

# -----------------------------------------------------------------------------

class CompressedSqliteDict(SqliteDict):
    """ overrides the encode/decode methods to use zlib, so we get compressed storage """

    def __init__(self, *args, **kwargs):

        def encode(obj):
            return sqlite3.Binary(zlib.compress(pickle.dumps(obj, pickle.HIGHEST_PROTOCOL)))

        def decode(obj):
            return pickle.loads(zlib.decompress(bytes(obj)))

        super().__init__(*args, **kwargs, encode=encode, decode=decode)

# -----------------------------------------------------------------------------

"""
some docs to self:
flag='c': default mode, open for read/write, and creating the db/table if necessary
flag='r': open for read-only
"""

PAPERS_DB_FILE = 'papers.db' # stores info about papers, and also their lighter-weight metadata
DICT_DB_FILE = 'dict.db' # stores account-relevant info, like which tags exist for which papers

def get_papers_db(flag='r', autocommit=True):
    assert flag in ['r', 'c']
    pdb = CompressedSqliteDict(PAPERS_DB_FILE, tablename='papers', flag=flag, autocommit=autocommit)
    return pdb

def get_metas_db(flag='r', autocommit=True):
    assert flag in ['r', 'c']
    mdb = SqliteDict(PAPERS_DB_FILE, tablename='metas', flag=flag, autocommit=autocommit)
    return mdb

def get_tags_db(flag='r', autocommit=True):
    assert flag in ['r', 'c']
    ddb = CompressedSqliteDict(DICT_DB_FILE, tablename='tags', flag=flag, autocommit=autocommit)
    return ddb
