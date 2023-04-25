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
import query_meetup
import yaml

def main():
    """
    Main execution
    """

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

    meetup_conn = query_meetup.MSMeetup(args.config)

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

    locations = {}
    # Horrible nested for loop to load dict of city, country
    for country in cfg['groups']['locations']:
        for location in cfg['groups']['locations'][country]:
            locations[location] = country

    # Set up filters data structure from config
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

    rate_limit = cfg['groups']['api_rate_limit']

    outputs = []
    for output in cfg['groups']['output']['types']:
        outputs.append(output)
    if 'xlsx' in outputs:
        sheet_name = cfg['groups']['output']['sheet_name']


    columns = OrderedDict([('Name', 'name'),
                           ('Members', 'members'),
                           ('City', 'city'),
                           ('Country', 'country'),
                           ('URL', 'link')])
    res = []

    ds_file = args.config+'.pkl'
    if os.path.isfile(ds_file):
        print("Found datastore on disk")
        with open(ds_file, "rb") as datastore:
            groups = pickle.load(datastore)
    else:
        groups = []

    # Search for groups
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
        time.sleep(rate_limit)
    for group_id in res:
        if groups and next((group for group in groups if group["id"] == group_id), None):
            print(f"Found group {[group['name'] for group in groups if group['id'] == group_id][0]} in datastore")
        else:
            print(f"Checking group data for {group_id}")
            group = meetup_conn.get_group(group_id)
            if meetup_conn.debug:
                print(group)
            if filters['name_filter'][0]:
                print("Applying name filter")
                if query_meetup.check_name_filter(cfg['groups']['search_keys'], group):
                    groups.append(group)
                    with open(ds_file, "wb") as datastore:
                        pickle.dump(groups, datastore)
                    time.sleep(rate_limit)
                else:
                    if meetup_conn.debug:
                        print(f"Group {group['name']} does not match name filter")
                    continue

    groups = [group for group in groups if group['id'] in res]

    print ("Deduplicating results")
    groups = query_meetup.de_dupe(groups)
    if meetup_conn.debug:
        table = query_meetup.create_table(columns, groups)
        print(table)

    print("Applying additional filters")
    if filters['member_filter'][0]:
        print ("Applying member filter")
        groups = query_meetup.filter_on_members(filters, groups)
        if meetup_conn.debug:
            table = query_meetup.create_table(columns, groups)
            print(table)
    if filters['event_filter'][0]:
        print ("Applying event filter")
        groups = query_meetup.filter_on_events(meetup_conn,
                                               filters,
                                               groups,
                                               rate_limit)
        columns['Total Events'] = 'number_events'
        if meetup_conn.debug:
            table = query_meetup.create_table(columns, groups)
            print(table)
    if filters['period_filter'][0]:
        print ("Applying period filter")
        groups = meetup_query.filter_on_period(meetup_conn,
                                               filters,
                                               groups,
                                               rate_limit)
        columns['Events in Period'] = 'number_in_period'
        columns['Period (months)'] = 'period'
        if meetup_conn.debug:
            table = query_meetup.create_table(columns, groups)
            print(table)
    if filters['freq_filter'][0]:
        print ("Applying frequency filter")
        groups = query_meetup.filter_on_freq(meetup_conn,
                                             filters,
                                             groups,
                                             rate_limit)
        columns['Frequency (days)'] = 'event_freq'
        if meetup_conn.debug:
            table = query_meetup.create_table(columns, groups)
            print(table)
    print ("Creating output")
    if 'xlsx' in outputs:
        query_meetup.create_spreadsheet(sheet_name, columns, groups)
    if 'table' in outputs:
        table = query_meetup.create_table(columns, groups)
        print(table)

if __name__ == "__main__":
    main()
