"""Scraping Open Journal Systems.

Usage:
  scholia.scrape.ojs journal_url_to_quickstatements <url>
  scholia.scrape.ojs scrape-paper-from-url <url>
  scholia.scrape.ojs issue-url-to-quickstatements [options] <url>
  scholia.scrape.ojs paper-url-to-q <url>
  scholia.scrape.ojs paper-url-to-quickstatements [options] <url>

Options:
  --iso639=iso639 Overwrite default iso639
  -o --output=file  Output filename, default output to stdout
  --oe=encoding     Output encoding [default: utf-8]

Examples
--------
$ python -m scholia.scrape.ojs paper-url-to-quickstatements \
    https://journals.uio.no/index.php/osla/article/view/5855

"""


import json

import os

import signal

from six import b, print_, u

from lxml import etree

import requests

from ..qs import paper_to_quickstatements
from ..query import iso639_to_q, issn_to_qs, SPARQL_ENDPOINT as WDQS_URL
from ..utils import escape_string, pages_to_number_of_pages

import ssl

#At least some sites are blocking scholia...
USER_AGENT = 'Scholia'
#USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'

HEADERS = {'User-Agent': USER_AGENT}

PAPER_TO_Q_QUERY = u("""
SELECT ?paper WHERE {{
  OPTIONAL {{ ?label rdfs:label "{label}"@en . }}
  OPTIONAL {{ ?title wdt:P1476 "{title}"@en . }}
  OPTIONAL {{ ?full_text_url wdt:P953 <{url}> . }}
  OPTIONAL {{ ?url wdt:P856 <{url}> . }}
  BIND(COALESCE(?full_text_url, ?url, ?label, ?title, ?doi) AS ?paper)
}}
""")

SHORT_TITLED_PAPER_TO_Q_QUERY = u("""
SELECT ?paper WHERE {{
  OPTIONAL {{ ?full_text_url wdt:P953 <{url}> . }}
  OPTIONAL {{ ?url wdt:P856 <{url}> . }}
  BIND(COALESCE(?full_text_url, ?url) AS ?paper)
}}
""")

ISSN_TO_Q_QUERY = u("""
SELECT DISTINCT ?journal WHERE {{
      ?journal wdt:P236 "{issn}" .
}}    
""")
Q_TO_DETAILS = u("""
SELECT DISTINCT  ?abbrev ?title  ?software  
   (GROUP_CONCAT(DISTINCT ?issn; SEPARATOR = "|") AS ?issns)
   (GROUP_CONCAT(DISTINCT ?rss; SEPARATOR = "|") AS ?rsss)
   (GROUP_CONCAT(DISTINCT ?website; SEPARATOR = "|") AS ?websites)
WHERE {{
  OPTIONAL {{ <http://www.wikidata.org/entity/{q}> wdt:P1019 ?rss }} .
  OPTIONAL {{ <http://www.wikidata.org/entity/{q}> wdt:P236 ?issn }} .
  OPTIONAL {{ <http://www.wikidata.org/entity/{q}> wdt:P1813 ?abbrev }} .
  OPTIONAL {{ <http://www.wikidata.org/entity/{q}> wdt:P1476 ?title }} .
  OPTIONAL {{ <http://www.wikidata.org/entity/{q}> wdt:P856 ?website  }} .
  OPTIONAL {{ <http://www.wikidata.org/entity/{q}> wdt:P408 ?software }} .
}} 
GROUP BY  ?abbrev ?title  ?software 
""")
                                                                                                                          
def issn_to_q(issn: str) ->  str: 
    """Find a wikidata item for an ISSN. """
    query = ISSN_TO_Q_QUERY.format(
        issn=issn)
    response = requests.get(WDQS_URL,
                            params={'query': query, 'format': 'json'},
                            headers=HEADERS)
    data = response.json()['results']['bindings']
    print(data)
    if len(data) == 0 or not data[0] or not data[0]['journal']:
        return ''
    q = str(data[0]['journal']['value'][31:])
    return q

def q_to_details(q: str) ->  str: 
    """Find journal core details for from a wikidata item. """
    query = Q_TO_DETAILS.format(
        q=q)
    response = requests.get(WDQS_URL,
                            params={'query': query, 'format': 'json'},
                            headers=HEADERS)
    ##print("q=" +  q)
    #print(Q_TO_DETAILS)
    #print(response.json())
    data = response.json()['results']['bindings']
    print(data)
    if len(data) == 0 or not data[0]:
        return ''
    return data

def is_OJS(tree) -> bool:
    """ Return true if soup is an OJS HTML page, checked three ways. """
    generatorOJS = len(tree.xpath("//meta[@name='generator']/@content[contains(.,'Open Journal Systems')]")) != 0
    libsOJS =  len(tree.xpath("//script/@src[contains(.,'/pkp/')]")) != 0 
    linksOJS = len(tree.xpath("//a/@href[contains(.,'/aboutThisPublishingSystem')]")) != 0
    pkpBlock = len(tree.xpath("//*/@class[contains(.,'pkp_block')]")) != 0
    print(" " + str(generatorOJS) + " /  " + str(libsOJS) + " / "  + str(linksOJS)  + " / "  + str(pkpBlock))
    #removing this link because many people remove the PKP/OJS branding
    #return generatorOJS and libsOJS and linksOJS
    return generatorOJS or libsOJS or linksOJS or pkpBlock
                                                                                                                           
def get_xpath_as_string(tree, xpath) -> str:
    """helper function to always return the first match as a string (possibly an empty string)"""
    lis = tree.xpath(xpath)
    if (len(lis) > 0):
        return lis[0]
    return ''


def journal_url_to_quickstatements(url: str, iso639=None) ->  str: 
    """Scrape a journal homepage and generate quickstatements

    """

    home_response = requests.get(url, headers=HEADERS, verify=False)
    home_tree = etree.HTML(home_response.content)

    redirected = home_response.url != url
    if (redirected):
        print ("redirected to" + home_response.url)
        return journal_url_to_quickstatements(home_response.url, iso639)
    
    issue_url = url + '/issue/current'
    if (is_OJS(home_tree)):
        issue_response = requests.get(issue_url, headers=HEADERS, verify=False)
        issue_tree = etree.HTML(issue_response.content)

        item_url = issue_tree.xpath("//a[contains(@href,'article/view')][1]/@href")[0]
        print("item_url= " + str(item_url))
        if (is_OJS(issue_tree)):
            item_response = requests.get(item_url, headers=HEADERS, verify=False)
            item_tree = etree.HTML(item_response.content)
            print(str(item_tree.xpath("//meta[contains(@name,'generator')]/@content")))                
            print(str(item_tree.xpath("//meta[contains(@name,'citation_journal_title')]/@content")))                
        
            if (is_OJS(item_tree)):

                lang =   get_xpath_as_string(item_tree,"/html/@lang")
                issn =   get_xpath_as_string(item_tree,"//meta[contains(@name,'citation_issn')]/@content")
                title =  get_xpath_as_string(item_tree,"//meta[contains(@name,'citation_journal_title')]/@content")
                abbrev = get_xpath_as_string(item_tree,"//meta[contains(@name,'citation_journal_abbrev')]/@content")

                if (issn == ''):
                    return "Sorry, not set up to deal with journals without an ISSN yet TODO"
                q = issn_to_q(issn)
                print(issn + " / " + title + " / " +  abbrev + " / " +  lang + " / " + q)
                data = q_to_details(q)

                result = "\n\n#begin quickstatements\n"
                if (q == ''):
                    result += '#there is no item for this journal, creating one\n'
                    result += 'CREATE\n'
                    result += 'LAST|Len|' + title + "\n"   #label (en = english)
                    if (abbrev) result += 'LAST|Aen|' + abbrev + "\n"  #alias (en = english)
                    result += "LAST|Den|Scientific journal called '" + title +"'\n"  #description (en = english)
                    q = 'LAST'
                else:
                    result += '#there is an item for this journal\n'

                    
                    
                return result + "#end quickstatemnts\n\nURL \"" + url + "\" appears lead to an OJS journal"



            
    print(etree.tostring(home_tree))
    return "XXXXXXXXXXXX URL  \"" + url + "\" does not appear lead to an OJS journal XXXXXXXXXXXXX"




def issue_url_to_paper_urls(url):
    """Scrape paper URLs from issue URL.

    Scrape paper (article) URLs from a given Open Journal System
    issue URL.

    Parameters
    ----------
    url : str
        URL to an OJS issue.

    Returns
    -------
    urls : list of strs
        List of URLs to papers.

    Notes
    -----
    Based on the URL, the HTML issue webpage will be fetched and the returned
    HTML parsed. Different matching approached are tried to extract the article
    URLs.

    """
    response = requests.get(url, headers=HEADERS)
    tree = etree.HTML(response.content)
    urls = tree.xpath("//div[@class='title']/a/@href")
    if len(urls) == 0:
        # This scheme seems to be used for version 3.2.1.4 of OJS
        urls = tree.xpath("//h3[@class='title']/a/@href")
    if len(urls) == 0:
        # This scheme is also used in version 3.2.1.4 of OJS
        # For instance, for https://tidsskrift.dk/bras/issue/view/9150
        urls = tree.xpath("//h3[@class='media-heading']/a/@href")
    if len(urls) == 0:
        # For instance, for
        # https://www.journals.vu.lt/scandinavistica/issue/view/1153
        urls = tree.xpath("//div[@class='article-summary-title']/a/@href")
    if len(urls) == 0:
        # Targeting specific class 'summary_title'
        urls = tree.xpath("//a[@class='summary_title']/@href")
    return urls


def issue_url_to_quickstatements(url, iso639=None):
    """Return Quickstatements for papers in an issue.

    From a Open Journal System issue URL extract metadata for individual
    papers and format them in the Quickstatement format for entry in
    Wikidata.

    Parameters
    ----------
    url : str
        URL for a OJS issue.
    iso639 : str, optional
        String with ISO639 code. Default is None, meaning the iso639 will be
        read from the metadata.

    Returns
    -------
    qs : str
        String with quickstatements.

    """
    paper_urls = issue_url_to_paper_urls(url)
    qs = ''
    for paper_url in paper_urls:
        qs += paper_url_to_quickstatements(paper_url, iso639=iso639) + "\n"
    return qs


def paper_to_q(paper):
    """Find Q identifier for paper.

    Parameters
    ----------
    paper : dict
        Paper represented as dictionary.

    Returns
    -------
    q : str or None
        Q identifier in Wikidata. None is returned if the paper is not found.

    Notes
    -----
    This function might be used to test if a scraped OJS paper is already
    present in Wikidata.

    The match on title is using an exact query, meaning that any variation in
    lowercase/uppercase will not find the Wikidata item. If the title is
    shorter than 21 character then only the URL is used to match.

    Examples
    --------
    >>> paper = {
    ...     'title': ('Linguistic Deviations in the Written Academic Register '
    ...               'of Danish University Students'),
    ...     'url': 'https://journals.uio.no/index.php/osla/article/view/5855'}
    >>> paper_to_q(paper)
    'Q61708017'

    """
    if 'title' in paper and len(paper['title']) > 20:
        title = escape_string(paper['title'])

        query = PAPER_TO_Q_QUERY.format(
            label=title, title=title,
            url=paper['url'])
    else:
        # The title is too short to match. Too many wrong matches.
        query = SHORT_TITLED_PAPER_TO_Q_QUERY.format(
            url=paper['url'])

    response = requests.get(WDQS_URL,
                            params={'query': query, 'format': 'json'},
                            headers=HEADERS)
    data = response.json()['results']['bindings']

    if len(data) == 0 or not data[0]:
        # Not found
        return None

    return str(data[0]['paper']['value'][31:])


def paper_url_to_q(url):
    """Return Q identifier based on URL.

    Scrape OJS HTML page with paper and use the extracted information on a
    query on Wikidata Query Service to find the Wikidata Q identifier.

    Parameters
    ----------
    url : str
        URL to Open Journal System article webpage.

    Returns
    -------
    q : str or None
        Q identifier for Wikidata or None if not found.

    Examples
    --------
    >>> url ='https://journals.uio.no/index.php/osla/article/view/5855'
    >>> paper_url_to_q(url)
    'Q61708017'

    """
    paper = scrape_paper_from_url(url)
    q = paper_to_q(paper)
    return q


def paper_url_to_quickstatements(url, iso639=None):
    """Scrape OJS paper and return quickstatements.

    Given a URL to a HTML web page representing a paper formatted by the Open
    Journal Systems, return quickstatements for data entry in Wikidata with the
    Magnus Manske Quickstatement tool.

    Parameters
    ----------
    url : str
        URL to OJS paper as a string.
    iso639 : str, optional
        String with ISO639 language code. Default is None, meaning the iso639
        will be read from the metadata.

    Returns
    -------
    qs : str
        Quickstatements for paper as a string.

    Notes
    -----
    It the paper is already entered in Wikidata then a comment will just
    be produced, - no quickstatements.

    The quickstatement tool is available at
    https://quickstatements.toolforge.org.

    """
    if url.endswith('/'):
        # remove trailing '/' from the URL
        url = url[:-1]

    paper = scrape_paper_from_url(url)

    if iso639 is not None:
        paper['iso639'] = iso639
        paper['language_q'] = iso639_to_q(iso639)

    q = paper_to_q(paper)
    if q:
        return "# {q} is {url}".format(q=q, url=url)

    qs = paper_to_quickstatements(paper)
    return qs


def scrape_paper_from_url(url):
    """Scrape OJS paper from URL.

    Arguments
    ---------
    url : str
        URL to paper as a string

    Returns
    -------
    paper : dict
        Paper represented as a dictionary.

    Example
    -------
    >>> url = 'https://tidsskrift.dk/carlnielsenstudies/article/view/27763'
    >>> paper = scrape_paper_from_url(url)
    >>> paper['authors'] == ['John Fellow']
    True

    """
    def _field_to_content(field):
        elements = tree.xpath("//meta[@name='{}']".format(field))
        if len(elements) == 0:
            return None
        content = elements[0].attrib['content']
        return content

    def _fields_to_content(fields):
        for field in fields:
            content = _field_to_content(field)
            if content is not None and content != '':
                return content

        return None

    entry = {'url': url}

    response = requests.get(url)
    tree = etree.HTML(response.content)

    authors = [
        author_element.attrib['content']
        for author_element in tree.xpath("//meta[@name='citation_author']")
    ]
    if len(authors) > 0:
        entry['authors'] = authors
    else:
        authors = [
            author_element.attrib['content']
            for author_element in
            tree.xpath("//meta[@name='DC.Creator.PersonalName']")
        ]
        if len(authors) > 0:
            entry['authors'] = authors

    title = _fields_to_content(['citation_title', 'DC.Title',
                                'DC.Title.Alternative'])
    if title is not None:
        q = paper_to_q(entry)
        if not q:  # If not identified before modification
            # Replace dash or colon without altering surrounding spaces
            modified_title = title.replace(" –", ":").replace("– ", ":")
            if modified_title != title:  # Check if replacement is made
                entry['title'] = modified_title
                q = paper_to_q(entry)
                if q:  # If identified after modification
                    # Plug in the modified title
                    entry['title'] = modified_title
                else:
                    entry['title'] = title  # Plug in the original title
            else:
                entry['title'] = title
        else:
            entry['title'] = title

    citation_date = _fields_to_content(['citation_date', 'DC.Date.issued'])
    if citation_date is not None:
        entry['date'] = citation_date.replace('/', '-')

    doi = _fields_to_content(['citation_doi', 'DC.Identifier.DOI'])
    if doi is not None:
        entry['doi'] = doi.upper()

    volume = _fields_to_content(['citation_volume', 'DC.Source.Volume'])
    if volume is not None:
        entry['volume'] = volume

    issue = _fields_to_content(['citation_issue', 'DC.Source.Issue'])
    if issue is not None:
        entry['issue'] = issue

    # Handle page information
    pages = None
    first_page = _field_to_content('citation_firstpage')
    last_page = _field_to_content('citation_lastpage')
    if first_page is not None and last_page is not None:
        pages = "{}-{}".format(first_page, last_page)
    else:
        pages = _field_to_content('DC.Identifier.pageNumber')
    if pages is not None:
        number_of_pages = pages_to_number_of_pages(pages)
        if number_of_pages is not None:
            entry['number_of_pages'] = number_of_pages

        pages_parts = pages.split('-')
        if len(pages_parts) == 2 and pages_parts[0] == pages_parts[1]:
            # One-page publication
            entry['pages'] = pages_parts[0]
        else:
            # Multiple pages
            entry['pages'] = pages

    pdf_url = _field_to_content('citation_pdf_url')
    if pdf_url is not None:
        entry['full_text_url'] = pdf_url
    else:
        pdf_urls = [
            element.attrib['href']
            for element in tree.xpath("//a[@class='obj_galley_link pdf']")
        ]
        if len(pdf_urls) > 0:
            entry['full_text_url'] = pdf_urls[0]

    # There may be inconsistent metadata for the language.
    # For for instance, https://tidsskrift.dk/sygdomogsamfund/article/view/579
    # "DC.Language" is correct, while "citation_language" is wrong.
    language_as_iso639 = _fields_to_content(
        ['DC.Language', 'citation_language'])
    if language_as_iso639 is not None:
        entry['iso639'] = language_as_iso639
        language_q = iso639_to_q(language_as_iso639)
        if language_q:
            entry['language_q'] = language_q

    published_in_title = _fields_to_content(
        ['citation_journal_title', 'DC.Source'])
    if published_in_title is not None:
        entry['published_in_title'] = published_in_title

    # Find journal/venue based on ISSN information
    issn = _fields_to_content(['citation_issn', 'DC.Source.ISSN'])
    if issn is not None:
        if len(issn) == 8:
            # Oslo Studies in Language OJS does not have a dash between the
            # numbers
            issn = issn[:4] + '-' + issn[4:]
        qs = issn_to_qs(issn)
        if len(qs) == 1:
            entry['published_in_q'] = qs[0]

    return entry


def main():
    """Handle command-line interface."""
    from docopt import docopt

    arguments = docopt(__doc__)

    if arguments['--iso639']:
        iso639 = arguments['--iso639']
    else:
        iso639 = None

    if arguments['--output']:
        output_filename = arguments['--output']
        output_file = os.open(output_filename, os.O_RDWR | os.O_CREAT)
    else:
        # stdout
        output_file = 1
    output_encoding = arguments['--oe']

    #turn off some ssl validation
    context = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
    context.verify_mode = ssl.CERT_NONE
    context.check_hostname = False
    context.load_default_certs()

    import urllib3
    urllib3.disable_warnings()

    # Ignore broken pipe errors
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    
    if arguments['journal_url_to_quickstatements']:
        url = arguments['<url>']
        qs = journal_url_to_quickstatements(url)
        os.write(output_file, qs.encode(output_encoding) + b('\n'))

    elif arguments['issue-url-to-quickstatements']:
        url = arguments['<url>']
        qs = issue_url_to_quickstatements(url, iso639=iso639)
        os.write(output_file, qs.encode(output_encoding) + b('\n'))

    elif arguments['paper-url-to-q']:
        url = arguments['<url>']
        entry = paper_url_to_q(url)
        print_(entry)

    elif arguments['paper-url-to-quickstatements']:
        url = arguments['<url>']
        qs = paper_url_to_quickstatements(url, iso639=iso639)
        os.write(output_file, qs.encode(output_encoding) + b('\n'))

    elif arguments['scrape-paper-from-url']:
        url = arguments['<url>']
        entry = scrape_paper_from_url(url)
        print_(json.dumps(entry))

    else:
        assert False


if __name__ == "__main__":
    main()
