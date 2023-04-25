#!/usr/bin/env python
"""
Query meetup.com API
"""
import os
import time
import argparse
import sys
from collections import OrderedDict
import pickle
import logging
import yaml
import query_meetup

def config_handler():
    '''
    Manage initial configuration parsing
    '''
    parser = argparse.ArgumentParser(description='Query Meetup.com')
    parser.add_argument('--config',
                        action="store",
                        dest="config",
                        help='configuration file to use',
                        required=True)
    args = parser.parse_args()

    if not os.path.isfile(args.config):
        print(f"Could not find config file {args.config}")
        sys.exit(1)

    # Handle group specific config
    with open(args.config, 'r', encoding='utf-8') as ymlfile:
        try:
            cfg = yaml.safe_load(ymlfile)
        except yaml.YAMLError as exc:
            print("Error parsing configuration file")
            if hasattr(exc, 'problem_mark'):
                mark = exc.problem_mark # pylint: disable=no-member
                print(f"Config file does not seem to be correct YAML - \
                        error at line {mark.line}, column {mark.column}")
                sys.exit(1)
    if "groups" not in cfg:
        print("Invalid configuration file")
        sys.exit(1)

    cfg['groups']['datastore'] = args.config+'.pkl'
    return args, cfg

def filter_handler(cfg):
    '''
    Set up filters data structure from config
    '''
    filters = {}
    filters['name_filter'] = [cfg['groups']['name_filter']]
    filters['member_filter'] = [cfg['groups']['member_filter'],
                                cfg['groups']['min_members']]
    filters['event_filter'] = [cfg['groups']['event_filter'],
                               cfg['groups']['min_events']]
    filters['freq_filter'] = [cfg['groups']['freq_filter'],
                              cfg['groups']['min_freq']]
    filters['period_filter'] = [cfg['groups']['period_filter'],
                                cfg['groups']['period'],
                                cfg['groups']['period_min']]
    return filters

def locations_handler(cfg):
    '''
    Handle locations
    '''
    locations = {}
    # Horrible nested for loop to load dict of city, country
    for country in cfg['groups']['locations']:
        for location in cfg['groups']['locations'][country]:
            locations[location] = country
    return locations

def check_for_data(ds_file):
    '''
    Check for existing data
    '''
    if os.path.isfile(ds_file):
        print("Found datastore on disk")
        with open(ds_file, "rb") as datastore:
            groups = pickle.load(datastore)
    else:
        groups = []
    return groups

def create_outputs(cfg, columns, groups):
    '''
    Create outputs
    '''
    outputs = []
    for output in cfg['groups']['output']['types']:
        outputs.append(output)
    if 'xlsx' in outputs:
        sheet_name = cfg['groups']['output']['sheet_name']
        query_meetup.create_spreadsheet(sheet_name, columns, groups)
    if 'table' in outputs:
        table = query_meetup.create_table(columns, groups)
        print(table)

def search_for_groups(meetup_conn, cfg):
    '''
    Search for groups
    '''
    locations = locations_handler(cfg)
    res = []
    for city, country in locations.items():
        print(f"Searching for groups in City: {city} Country: {country}")
        search_string = ' OR '.join(cfg['groups']['search_keys'])
        res += meetup_conn.search_for_groups(cfg['groups']['geonames_user'],
                                             city,
                                             country,
                                             cfg['groups']['radius'],
                                             search_string)
        if not res:
            print("No results for City: {city}, Country: {country}")
        time.sleep(cfg['groups']['api_rate_limit'])
    return res

def check_groups(meetup_conn,
                 cfg,
                 filters,
                 res):
    '''
    Check groups
    '''
    groups = check_for_data(cfg['groups']['datastore'])
    for group_id in res:
        if groups and next((group for group in groups if group["id"] == group_id), None):
            group_name = [group['name'] for group in groups if group['id'] == group_id][0]
            print(f"Found {group_name} in datastore")
        else:
            print(f"Checking group data for {group_id}")
            group = meetup_conn.get_group(group_id)
            logging.debug(group)
            if filters['name_filter'][0]:
                if query_meetup.check_name_filter(cfg['groups']['search_keys'], group):
                    groups.append(group)
                    with open(cfg['groups']['datastore'], "wb") as datastore:
                        pickle.dump(groups, datastore)
                    time.sleep(cfg['groups']['api_rate_limit'])
                else:
                    logging.debug("Group %s does not match name filter", group['name'])
                    continue

    groups = [group for group in groups if group['id'] in res]
    return groups

def main():
    """
    Main execution
    """

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    columns = OrderedDict([('Name', 'name'),
                           ('Members', 'members'),
                           ('City', 'city'),
                           ('Country', 'country'),
                           ('URL', 'link')])

    args, cfg = config_handler()

    meetup_conn = query_meetup.MSMeetup(args.config)

    # Set up filters data structure from config
    filters = filter_handler(cfg)

    rate_limit = cfg['groups']['api_rate_limit']

    # Search for groups
    res = search_for_groups(meetup_conn, cfg)

    groups = check_groups(meetup_conn, cfg, filters, res)

    print ("Deduplicating results")
    groups = query_meetup.de_dupe(groups)
    logging.debug(query_meetup.create_table(columns, groups))

    if filters['member_filter'][0]:
        print ("Applying member filter")
        groups = query_meetup.filter_on_members(filters, groups)
        logging.debug(query_meetup.create_table(columns, groups))
    if filters['event_filter'][0]:
        print ("Applying event filter")
        groups = query_meetup.filter_on_events(meetup_conn,
                                               filters,
                                               groups,
                                               rate_limit)
        columns['Total Events'] = 'number_events'
        logging.debug(query_meetup.create_table(columns, groups))
    if filters['period_filter'][0]:
        print ("Applying period filter")
        groups = query_meetup.filter_on_period(meetup_conn,
                                               filters,
                                               groups,
                                               rate_limit)
        columns['Events in Period'] = 'number_in_period'
        columns['Period (months)'] = 'period'
        logging.debug(query_meetup.create_table(columns, groups))
    if filters['freq_filter'][0]:
        print ("Applying frequency filter")
        groups = query_meetup.filter_on_freq(meetup_conn,
                                             filters,
                                             groups,
                                             rate_limit)
        columns['Frequency (days)'] = 'event_freq'
        logging.debug(query_meetup.create_table(columns, groups))

    print ("Creating output")
    create_outputs(cfg, columns, groups)

if __name__ == "__main__":
    main()
