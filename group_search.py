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

DATASTORE = 'test.data'

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

    meetup_query = query_meetup.MSMeetup(args.config)
    columns = OrderedDict([('Name', 'name'),
                           ('Members', 'members'),
                           ('City', 'city'),
                           ('Country', 'country'),
                           ('URL', 'link')])

    res = []

    if os.path.isfile(DATASTORE):
        print("Found datastore on disk")
        with open(DATASTORE, "rb") as datastore:
            groups = pickle.load(datastore)
    else:
        groups = []

    # Get Oauth token
    meetup_query.get_oauth_token()
    # Search for groups
    for city, country in meetup_query.locations.items():
        print(f"Searching for groups in City: {city} Country: {country}")
        res += meetup_query.search_for_groups(city, country)
        if not res:
            print("No results for City: {city}, Country: {country}")
        time.sleep(meetup_query.api_rate_limit)
    for group_id in res:
        if groups and next((group for group in groups if group["id"] == group_id), None):
            print(f"Found group {[group['name'] for group in groups if group['id'] == group_id][0]} in datastore")
        else:
            print(f"Checking group data for {group_id}")
            group = meetup_query.get_group(group_id)
            if meetup_query.debug:
                print(group)
            if meetup_query.filters['name_filter'][0]:
                if meetup_query.check_name_filter(group):
                    groups.append(group)
                    with open(DATASTORE, "wb") as datastore:
                        pickle.dump(groups, datastore)
                    time.sleep(meetup_query.api_rate_limit)
                else:
                    if meetup_query.debug:
                        print(f"Group {group['name']} does not match name filter")
                    continue

    groups = [group for group in groups if group['id'] in res]

    print ("Deduplicating results")
    groups = query_meetup.de_dupe(groups)
    if meetup_query.debug:
        table = query_meetup.create_table(columns, groups)
        print(table)

    print("Applying filters")
    if meetup_query.filters['name_filter'][0]:
        print ("Applying name filter")
        groups = meetup_query.filter_on_name(groups)
        if meetup_query.debug:
            table = query_meetup.create_table(columns, groups)
            print(table)
    if meetup_query.filters['member_filter'][0]:
        print ("Applying member filter")
        groups = meetup_query.filter_on_members(groups)
        if meetup_query.debug:
            table = query_meetup.create_table(columns, groups)
            print(table)
    if meetup_query.filters['event_filter'][0]:
        print ("Applying event filter")
        groups = meetup_query.filter_on_events(groups)
        columns['Total Events'] = 'number_events'
        if meetup_query.debug:
            table = query_meetup.create_table(columns, groups)
            print(table)
    if meetup_query.filters['period_filter'][0]:
        print ("Applying period filter")
        groups = meetup_query.filter_on_period(groups)
        columns['Events in Period'] = 'number_in_period'
        columns['Period (months)'] = 'period'
        if meetup_query.debug:
            table = query_meetup.create_table(columns, groups)
            print(table)
    if meetup_query.filters['freq_filter'][0]:
        print ("Applying frequency filter")
        groups = meetup_query.filter_on_freq(groups)
        columns['Frequency (days)'] = 'event_freq'
        if meetup_query.debug:
            table = query_meetup.create_table(columns, groups)
            print(table)
    print ("Creating output")
    if 'xlsx' in meetup_query.outputs:
        query_meetup.create_spreadsheet(meetup_query.sheet_name, columns, groups)
    if 'table' in meetup_query.outputs:
        table = query_meetup.create_table(columns, groups)
        print(table)

if __name__ == "__main__":
    main()
