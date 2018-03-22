from datetime import datetime
import pandas as pd
import re
import gzip
import os
import tarfile
import urllib.request
import xml.etree.cElementTree as ElementTree
try:
    import cPickle as pickle
except ImportError:
    import pickle

DATA_PATH = 'data'
RDFFILES = os.path.join(DATA_PATH, 'rdf-files.tar.bz2') # The catalog downloaded from Gutenberg
RDFURL = r'http://www.gutenberg.org/cache/epub/feeds/rdf-files.tar.bz2'
META_FIELDS = ('id', 'author', 'title', 'downloads', 'LCC',
    'subjects', 'authoryearofbirth', 'authoryearofdeath')
NS = dict(
    pg='http://www.gutenberg.org/2009/pgterms/',
    dc='http://purl.org/dc/terms/',
    dcam='http://purl.org/dc/dcam/',
    rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#')
LINEBREAKRE = re.compile(r'[ \t]*[\n\r]+[ \t]*')
ETEXTRE = re.compile(r'''
    e(text|b?ook)
    \s*
    (\#\s*(?P<etextid_front>\d+)
    |
    (?P<etextid_back>\d+)\s*\#)
    ''', re.IGNORECASE | re.VERBOSE)

def readmetadata(num_books=None):
    if num_books:
        file_name = os.path.join(DATA_PATH, str(num_books) + '.metadata.pkl.gz')
    else:
        file_name = os.path.join(DATA_PATH, 'allbooks.metadata.pkl.gz')
        
    if os.path.exists(file_name):
        metadata = pickle.load(gzip.open(file_name, 'rb'))
    else:
        metadata = pd.DataFrame() # Set to empty for good reasons
        for counter, xml in enumerate(getrdfdata()):
            if num_books and counter >= num_books:
                return metadata
            ebook = xml.find(r'{%(pg)s}ebook' % NS)
            if ebook is None:
                continue
            result = parsemetadata(ebook)
            if result is not None:
                result = pd.DataFrame.from_dict(result, orient='index').transpose()
                if not metadata.empty:
                    # Not doing this in-place because using loc feels hacky
                    metadata = metadata.append(result, ignore_index=True)
                else:      
                    metadata = result
        pickle.dump(metadata, gzip.open(file_name, 'wb'), protocol=-1)
    return metadata

def getrdfdata():
    if not os.path.exists(RDFFILES):
        _, _ = urllib.request.urlretrieve(RDFURL, RDFFILES)
    with tarfile.open(RDFFILES) as archive:
        for tarinfo in archive:
            yield ElementTree.parse(archive.extractfile(tarinfo))

def parsemetadata(ebook):
    result = dict.fromkeys(META_FIELDS)
    # get etext no
    about = ebook.get('{%(rdf)s}about' % NS)
    result['id'] = int(os.path.basename(about))
    # author
    creator = ebook.find('.//{%(dc)s}creator' % NS)
    if creator is not None:
        name = creator.find('.//{%(pg)s}name' % NS)
        if name is not None:
            result['author'] = safeunicode(name.text, encoding='utf-8')
        birth = creator.find('.//{%(pg)s}birthdate' % NS)
        if birth is not None:
            result['authoryearofbirth'] = int(birth.text)
        death = creator.find('.//{%(pg)s}deathdate' % NS)
        if death is not None:
            result['authoryearofdeath'] = int(death.text)
    # title
    title = ebook.find('.//{%(dc)s}title' % NS)
    if title is not None:
        result['title'] = fixsubtitles(
                safeunicode(title.text, encoding='utf-8'))
    # subject lists
    result['subjects'], result['LCC'] = set(), set()
    for subject in ebook.findall('.//{%(dc)s}subject' % NS):
        res = subject.find('.//{%(dcam)s}memberOf' % NS)
        if res is None:
            continue
        res = res.get('{%(rdf)s}resource' % NS)
        value = subject.find('.//{%(rdf)s}value' % NS).text
        if res == ('%(dc)sLCSH' % NS):
            result['subjects'].add(value)
        elif res == ('%(dc)sLCC' % NS):
            result['LCC'].add(value)
            
    # download count
    downloads = ebook.find('.//{%(pg)s}downloads' % NS)
    if downloads is not None:
        result['downloads'] = int(downloads.text)
    return result

def etextno(lines):
    for line in lines:
        match = ETEXTRE.search(line)
        if match is not None:
            front_match = match.group('etextid_front')
            back_match = match.group('etextid_back')
            if front_match is not None:
                return int(front_match)
            elif back_match is not None:
                return int(back_match)
            else:
                raise ValueError('no regex match (this should never happen')
    raise ValueError('no etext-id found')

def fixsubtitles(title):
    tmp = LINEBREAKRE.sub(': ', title, 1)
    return LINEBREAKRE.sub('; ', tmp)

def safeunicode(arg, *args, **kwargs):
    """Coerce argument to unicode, if it's not already."""
    return arg if isinstance(arg, str) else str(arg, *args, **kwargs)

