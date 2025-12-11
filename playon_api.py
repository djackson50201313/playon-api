#!/usr/bin/env python
import re
import json
import mechanize
import xml.etree.ElementTree as ET
from pathlib import Path

def load_config():
    config_path = Path(__file__).parent / 'config.json'
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        config['server']['base_url'] = config['server']['base_url'].format(
            ip=config['server']['ip'],
            port=config['server']['port']
        )
        return config
    except FileNotFoundError:
        print(f"Error: Configuration file not found at {config_path}")
        raise
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in configuration file {config_path}")
        raise
    except KeyError as e:
        print(f"Error: Missing required configuration key: {e}")
        raise

# Load configuration
config = load_config()
base_url = config['server']['base_url']

def get_providers(server=None):
    if server is None:
        server = config['server']['ip']
    br = mechanize.Browser()
    br.set_handle_robots(False)
    response = br.open(f"{base_url}/data/data.xml")
    page_source = response.read()
    # Use BeautifulSoup for parsing
    #soup = BeautifulSoup(page_source, 'xml.parser')
    #print(soup.findall('group', href_='/data/data.xml?id='))
    root = ET.fromstring(page_source)
    # Process group elements
    providers = {}
    for group in root.findall('group'):
        if group.get('id'):
            providers[group.get('name')] = {'href':group.get('href'), 'id':group.get('id')}
    return providers

def query_provider(provider, search_term, server=None):
    if server is None:
        server = config['server']['ip']
    br = mechanize.Browser()
    br.set_handle_robots(False)
    url = f"{base_url}/data/data.xml?id={provider}&searchterm={search_term}"
    print(url)
    results = []
    try:
        response = br.open(url)
        page_source = response.read()
        root = ET.fromstring(page_source)
        for ea_result in root.findall('group'):
            if 'id' in ea_result:
                #This means it's the parent with the provider, so skip
                continue
            else:
                results.append({'href':ea_result.get('href'), 'name':ea_result.get('name'), 'provider':provider, 'type':ea_result.get('type')})
                #print(f"{ea_result.get('name')} - {ea_result.get('type')} - {ea_result.get('href')}")
    except Exception as e:
        print(e)
    return results

def trace_folder(result, server=None):
    if server is None:
        server = config['server']['ip']
    br = mechanize.Browser()
    br.set_handle_robots(False)
    url = f"{base_url}{result['href']}"
    #print(url)
    search_results = []
    try:
        response = br.open(url)
        page_source = re.sub(r'^[^<]+','',response.read().decode('utf-8', errors='ignore'))
        root = ET.fromstring(page_source)
        groups_found = 0
        for ea_result in root.findall('group'):
            if ea_result.get('href') == result['href']:
                continue # This means it's the same page we're looking at
            elif ea_result.get('childs', None) is not None:
                search_results.extend(trace_folder(ea_result, server)) # Nested folders
            elif ea_result.get('type') == 'video':
                search_results.append(ea_result)
            else:
                print(f"Unknown result type: {ea_result}")
            groups_found += 1
        #print(groups_found)
        if groups_found == 0:
            #print(root.findall('.//'))
            return [result]
    except Exception as e:
        print(e)
    #print(search_results)
    return search_results


def single_match(result, pattern, media_type, server=None):
    if server is None:
        server = config['server']['ip']
    if pattern.match(result['name']):
        if result['type'] == 'folder':
            results = trace_folder(result=result, server=server)
            if len(results) >2 and media_type == 'show':
                return True
            elif media_type == 'movie':
                #print(f"\t\t{result['name']} - {result['type']} - {result['href']}")
                return True
            else:
                return False
        elif result['type'] == 'video':
            if media_type == 'show':
                return False
            else:
                return True
        else:
            print(f"What kind of type is this??? {result['type']}")
    else:
        #print(f"{result['name']} doesn't match {pattern}")
        return False

def filter_results(results, search_term, media_type, match_type):
    # Set pattern for title matching
    #print(f"Matching pattern: {search_term}")
    pattern = re.compile(".*" + search_term, re.IGNORECASE)
    if match_type == 'exact':
        pattern = re.compile("^%s$" % search_term, re.IGNORECASE)

    filtered_results = []
    for result in results:
        #print(f"Checking {result['name']}")
        if single_match(result, pattern, media_type):
            filtered_results.append(result)
            #print(f"\t{result['name']} MATCHES!")


    return filtered_results

def add_to_record(result, server=None):
    if server is None:
        server = config['server']['ip']
    final_links = trace_folder(result=result, server=server)
    br = mechanize.Browser()
    br.set_handle_robots(False)
    for ea_link in final_links:
        #print(ea_link)
        url = f"http://{server}:54479{ea_link.get('href')}"
        #print(url)
        try:
            response = br.open(url)
            page_source = response.read()
            root = ET.fromstring(page_source)
            for ea_result in root.findall('media_playlater'):
                response = br.open(ea_result.get('src'))
                page_source = response.read()
                #print(page_source)
        except Exception as e:
            print(e)



if __name__ == '__main__':
    import sys
    import json
    import argparse

    parser = argparse.ArgumentParser(description="playonapi.") #TODO: update
    parser.add_argument("--providers", action="store_true", default=False, help="Show providers and exit")
    parser.add_argument("--exact", action="store_true", default=False, help="Include a greeting message.")
    parser.add_argument("--media", default='show', help="only specific types of media")
    parser.add_argument('search_term', nargs='*',
                        help='One or more text arguments.')
    parser.add_argument("--exclude", dest='excluded_providers', default='', action="append", help="exclude provider(s). Specify multiple with ")
    parser.add_argument("--record", action="store_true", default=False, help="add to record queue automatically")
    args = parser.parse_args()

    if args.media not in ('show', 'movie'):
        sys.exit("media must be 'show' or 'movie'")

    if args.providers:
        providers = get_providers(server="127.0.0.1")
        sys.exit('\n'.join(providers))

    providers = get_providers()
    filtered_results = []
    for ea_provider in providers:
        if ea_provider in args.excluded_providers:
            continue
        print(f"Looking up search term in {ea_provider}")
        url_search_term = '%20'.join(args.search_term)
        text_search_term = ' '.join(args.search_term)
        results = query_provider(providers[ea_provider]['id'], url_search_term)
        print(f"Found {len(results)} results for {text_search_term} in {ea_provider}")
        filtered_results.extend(filter_results(results, text_search_term, args.media, args.exact))
    for ea_result in filtered_results:
        print(f"Found result: {ea_result}")
        if args.record:
            print(f"Writing to record queue")
            add_to_record(ea_result)

