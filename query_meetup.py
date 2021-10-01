#!/usr/bin/env python
"""
Query meetup.com API
"""

import os
import time
import argparse
import sys
import datetime
from collections import OrderedDict
import requests
from dateutil.parser import parse
import pytz
import yaml
import xlsxwriter
import geocoder
from prettytable import PrettyTable

def de_dupe(groups):
    """
    De-duplicate a set of groups
    """
    deduped = [i for n, i in enumerate(groups) if i not in groups[n+1:]]
    return deduped

def exclude_by_country(groups, country):
    """
    Strip out groups with a different country
    """
    excluded = [group for group in groups if group["country"] == country]
    return excluded

def event_frequency(datetimes):
    """
    Given a set of datetimes calculate the average frequency of events in days
    """
    timedeltas = [datetimes[i+1]-datetimes[i] for i in range(0, len(datetimes)-1, 1)]
    average_timedelta = sum(timedeltas, datetime.timedelta(0)) / len(timedeltas)
    return average_timedelta.days

def number_in_period(datetimes, period):
    """
    Given a set of datetimes calculate the number of events within a period
    Not wildly accurate given days in month varies
    """
    count = 0
    # Assume period is in months, so convert to days
    days = period * 30.436875
    # Handle timezone awareness
    time_start = datetime.datetime.now(pytz.utc) - datetime.timedelta(days=days)
    for i in range(0, len(datetimes), 1):
        if datetimes[i] > time_start:
            count += 1
    return count

def create_spreadsheet(name, columns, groups):
    """
    Create a spreadsheet from a set of groups and column headers
    """
    # sanitise name from config
    if not name.endswith('.xlxs'):
        name = name+".xlsx"
    workbook = xlsxwriter.Workbook(name)
    row_count = {}
    col_widths = {}
    for group in groups:
        current_sheet = workbook.get_worksheet_by_name(group['country'])
        if not current_sheet:
            current_sheet = workbook.add_worksheet(group['country'])
            # Set the values for initial column widths from the column headings length
            col_widths[group['country']] = add_columns(workbook, current_sheet, columns.keys())
            row_count[group['country']] = 0
        col = 0
        for item in columns.values():
            # Update the column widths dictionary as we iterate through
            # Set it to widest item
            if isinstance(group[item], int):
                length = len(str(group[item]))
            else:
                length = len(group[item])
            if length > col_widths[group['country']][col]:
                col_widths[group['country']][col] = length
            current_sheet.write(row_count[group['country']] + 1, col, group[item])
            col += 1
        # store the current row per sheet in case data is out of order
        row_count[group['country']] += 1
    # Set column widths to display properly
    for sheet, values in col_widths.iteritems():
        current_sheet = workbook.get_worksheet_by_name(sheet)
        for col, value in enumerate(values):
            current_sheet.set_column(col, col, value + 1)
    workbook.close()

def add_columns(workbook, worksheet, columns):
    """
    Add columns to a worksheet
    """
    bold = workbook.add_format({'bold': True})
    col = 0
    col_widths = []
    for item in columns:
        worksheet.write(0, col, item, bold)
        col_widths.append(len(str(item)))
        col += 1
    return col_widths

def create_table(columns, groups):
    """
    Create a table from a set of groups and column headers
    """
    table = PrettyTable(columns.keys())
    for group in groups:
        row = []
        for item in columns.values():
            row.append(group[item])
        table.add_row(row)
    return table

class MSMeetup(object):
    """
    Define class object and load config
    """
    def __init__(self, configfile):
        with open(configfile, 'r') as ymlfile:
            try:
                cfg = yaml.safe_load(ymlfile)
            except yaml.YAMLError as exc:
                print "Error parsing configuration file"
                if hasattr(exc, 'problem_mark'):
                    mark = exc.problem_mark # pylint: disable=no-member
                    print "Config file does not seem to be correct YAML - \
                            error at line %s, column %s" \
                            % (mark.line, mark.column)
                sys.exit(1)
        if "meetup" not in cfg:
            print "Invalid configuration file"
            sys.exit(1)
        self.client_id = cfg['meetup']['client_id']
        self.auth_url = cfg['meetup']['auth_url']
        self.client_secret = cfg['meetup']['client_secret']
        self.access_url = cfg['meetup']['access_url']
        self.email = cfg['meetup']['email']
        self.password = cfg['meetup']['password']
        self.geonames_user = cfg['meetup']['geonames_user']
        self.oauth_url = cfg['meetup']['oauth_url']
        self.base_api_url = cfg['meetup']['base_api_url']
        self.redirect_uri = cfg['meetup']['redirect_uri']
        self.api_rate_limit = cfg['meetup']['api_rate_limit']
        self.radius = cfg['meetup']['radius']
        self.search_keys = cfg['meetup']['search_keys']
        self.filters = {}
        self.filters['name_filter'] = [cfg['meetup']['name_filter']]
        self.filters['member_filter'] = [cfg['meetup']['member_filter'],
                                         cfg['meetup']['min_members']]
        self.filters['event_filter'] = [cfg['meetup']['event_filter'],
                                        cfg['meetup']['min_events']]
        self.filters['freq_filter'] = [cfg['meetup']['freq_filter'],
                                       cfg['meetup']['min_freq']]
        self.filters['period_filter'] = [cfg['meetup']['period_filter'],
                                         cfg['meetup']['period'],
                                         cfg['meetup']['period_min']]
        self.debug = cfg['meetup']['debug']
        self.outputs = []
        for output in cfg['output']['types']:
            self.outputs.append(output)
        if 'xlsx' in self.outputs:
            self.sheet_name = cfg['output']['sheet_name']
        self.locations = {}
        # Horrible nested for loop to load dict of city, country
        for country in cfg['locations']:
            for location in cfg['locations'][country]:
                self.locations[location] = country

    def get_oauth_token(self):
        """
        Get an Oauth token
        """
        grant_type = 'anonymous_code'
        headers = {'Accept': 'application/json'}
        auth_params = {'client_id': self.client_id,
                       'response_type': grant_type,
                       'redirect_uri': self.redirect_uri}
        print "Attempting to authenticate against Meetup.com"
        try:
            auth_response = requests.get(self.auth_url, params=auth_params, headers=headers)
        except requests.exceptions.RequestException as error:
            raise SystemExit(error)
        auth_token = auth_response.json()["code"]
        # Request access token
        access_params = {'client_id': self.client_id,
                         'client_secret': self.client_secret,
                         'grant_type': grant_type,
                         'redirect_uri': self.redirect_uri,
                         'code': auth_token}
        try:
            access_response = requests.post(self.access_url, params=access_params, headers=headers)
        except requests.exceptions.RequestException as error:
            raise SystemExit(error)
        access_token = access_response.json()["access_token"]
        # Request oauth token
        access_token_string = 'Bearer %s' % access_token
        headers['Authorization'] = access_token_string
        oauth_params = {'email': self.email, 'password': self.password}
        try:
            oauth_response = requests.post(self.oauth_url, params=oauth_params, headers=headers)
        except requests.exceptions.RequestException as error:
            raise SystemExit(error)
        print "Successfully authenticated against Meetup.com"
        auth_string = 'Bearer %s' % oauth_response.json()["oauth_token"]
        oauth_headers = {'Accept': 'application/json', 'Authorization': auth_string}
        self.oauth_headers = oauth_headers

    def get_lat_lon(self, city, country):
        """
        Get a city's lat and lon using Geonames
        """
        try:
            geodata = geocoder.geonames(city, country=country, key=self.geonames_user)
        except requests.exceptions.RequestException as error:
            print "Could not connect to geocoding API - exiting"
            raise SystemExit(error)
        if geodata.ok:
            return geodata.lat, geodata.lng
        print "No Geocode results found for %s %s" % (city, country)
        return False, False

    def graphql_query(self, query):
        """
        Query the GraphQL API
        """
        res = requests.post(self.base_api_url, json={'query': query}, headers=self.oauth_headers)
        return res.json()

    def search_for_groups(self, city, country):
        """
        Search for groups
        """
        lat, lon = self.get_lat_lon(city, country)
        if all([lat, lon]):
            search_string = ' OR '.join(self.search_keys)
            query = """query {
                keywordSearch(filter: { query: "%s", lat: %s, lon: %s, radius: %s, source: GROUPS }) {
                    count
                    pageInfo {
                        endCursor
                    }
                    edges {
                        node {
                            id
                        }
                    }
                }   
            }""" % (search_string, lat, lon, self.radius)
            res = self.graphql_query(query)
            ids = [x for y in [item['node'].values()
                               for item in res['data']['keywordSearch']['edges']]
                   for x in y]
            return ids
        return []

    def get_group(self, group_id):
        """
        Retrieve the group info
        """
        query = """query {
            group(id: %s) {
                name
                link
                city
                country
                memberships {
                    count 
                }
             }
          }""" % (group_id)
        res = self.graphql_query(query)
        res['data']['group']['id'] = group_id
        res['data']['group']['members'] = res['data']['group']['memberships']['count']
        del res['data']['group']['memberships']
        return res['data']['group']

    def get_number_of_events(self, group_id):
        """
        Retrieve the number of events for a group
        """
        query = """query {
            group(id: %s) {
                unifiedEvents {
                    count
                    pageInfo {
                        endCursor
                    }
                    edges {
                        node {
                            id
                        }
                    }
               }
            }
          }""" % (group_id)
        res = self.graphql_query(query)
        return res['data']['group']['unifiedEvents']['count']

    def get_members(self, group_id):
        """
        Retrieve the members of a group
        """
        query = """query {
            group(id: %s) {
                memberships {
                    count
                    pageInfo {
                        endCursor
                    }
                    edges {
                        node {
                            id
                            name
                        }
                    }
               }
            }
          }""" % (group_id)
        res = self.graphql_query(query)
        return res

    def get_event_datetimes(self, group_id):
        """
        Get a list of datetimes for events
        """
        query = """query {
            group(id: %s) {
                unifiedEvents {
                    count
                    pageInfo {
                        endCursor
                    }
                    edges {
                        node {
                            dateTime
                        }
                    }
               }
            }
          }""" % (group_id)
        res = self.graphql_query(query)
        datetime_strings = [x for y in [item['node'].values()
                                        for item in
                                        res['data']['group']['unifiedEvents']['edges']]
                            for x in y]
        # These are unicode strings so convert them to datetimes
        datetimes = []
        for dt_string in datetime_strings:
            # Use parse as strptime doesn't support TZ offsets
            date_time = parse(dt_string)
            datetimes.append(date_time)
        return datetimes

    def filter_on_name(self, groups):
        """
        Return a filtered set of groups based on name matching
        Meetup API search scope is full description not just name
        """
        name_matches = [group for group in groups
                        if any(key.lower() in group["name"].lower()
                               for key in self.search_keys)]
        return name_matches

    def filter_on_members(self, groups):
        """
        Return a filtered set of groups based on number of members
        """
        mem_filter = [group for group in groups
                      if group["members"] > self.filters['member_filter'][1]]
        return mem_filter

    def filter_on_events(self, groups):
        """
        Return a filtered set of groups based on minimum number of events
        """
        for group in groups:
            group["number_events"] = self.get_number_of_events(group['id'])
            time.sleep(self.api_rate_limit)
        num_event_filter = [group for group in groups
                            if group["number_events"] > self.filters['event_filter'][1]]
        return num_event_filter

    def filter_on_period(self, groups):
        """
        Return a filtered set of groups based on events in past configurable period
        """
        for group in groups:
            group["number_in_period"] = number_in_period(self.get_event_datetimes(group['id']),
                                                         self.filters['period_filter'][1])
            group["period"] = self.filters['period_filter'][1]
            time.sleep(self.api_rate_limit)
        period_event_filter = [group for group in groups
                               if group["number_in_period"]
                               > self.filters['period_filter'][2]]
        return period_event_filter

    def filter_on_freq(self, groups):
        """
        Return a filtered set based on a configurable past event frequency
        """
        for group in groups:
            datetimes = self.get_event_datetimes(group['id'])
            group["event_freq"] = event_frequency(datetimes)
            time.sleep(self.api_rate_limit)
        event_freq_filter = [group for group in groups
                             if group["event_freq"]
                             < self.filters['freq_filter'][1]]
        return event_freq_filter

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
        print "Could not find config file %s" % args.config
        sys.exit(1)

    meetup_query = MSMeetup(args.config)
    columns = OrderedDict([('Name', 'name'),
                           ('Members', 'members'),
                           ('City', 'city'),
                           ('Country', 'country'),
                           ('URL', 'link')])

    res = []
    groups = []
    # Get Oauth token
    meetup_query.get_oauth_token()
    # Search for groups
    for city, country in meetup_query.locations.iteritems():
        print "Searching for groups in City: %s Country: %s" % (city, country)
        res += meetup_query.search_for_groups(city, country)
        if not res:
            print "No results for City: %s, Country: %s" % (city, country)
        time.sleep(meetup_query.api_rate_limit)
    for group_id in res:
        print "Populating group data for id %s" % group_id
        group = meetup_query.get_group(group_id)
        if meetup_query.debug:
            print group
        groups.append(group)
        time.sleep(meetup_query.api_rate_limit)
    print "Deduplicating results"
    groups = de_dupe(groups)
    print "Applying filters"
    if meetup_query.filters['name_filter'][0]:
        print "Applying name filter"
        groups = meetup_query.filter_on_name(groups)
    if meetup_query.filters['member_filter'][0]:
        print "Applying member filter"
        groups = meetup_query.filter_on_members(groups)
    if meetup_query.filters['event_filter'][0]:
        print "Applying event filter"
        groups = meetup_query.filter_on_events(groups)
        columns['Total Events'] = 'number_events'
    if meetup_query.filters['period_filter'][0]:
        print "Applying period filter"
        groups = meetup_query.filter_on_period(groups)
        columns['Events in Period'] = 'number_in_period'
        columns['Period (months)'] = 'period'
    if meetup_query.filters['freq_filter'][0]:
        print "Applying frequency filter"
        groups = meetup_query.filter_on_freq(groups)
        columns['Frequency (days)'] = 'event_freq'
    print "Creating output"
    if 'xlsx' in meetup_query.outputs:
        create_spreadsheet(meetup_query.sheet_name, columns, groups)
    if 'table' in meetup_query.outputs:
        table = create_table(columns, groups)
        print table

if __name__ == "__main__":
    main()
