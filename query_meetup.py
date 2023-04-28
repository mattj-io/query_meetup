#!/usr/bin/env python
"""
Query meetup.com API
"""

import time
import sys
import datetime
import requests
from dateutil.parser import parse
import pytz
import yaml
import xlsxwriter
import geocoder
from prettytable import PrettyTable

BASE_API_URL = 'https://api.meetup.com/gql'
ACCESS_URL = 'https://secure.meetup.com/oauth2/access'
AUTH_URL = 'https://secure.meetup.com/oauth2/authorize'
DEBUG = False

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
    for sheet, values in col_widths.items():
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

class MSMeetup:
    """
    Define class object and load config
    """
    def __init__(self, configfile):
        with open(configfile, 'r', encoding='utf-8') as ymlfile:
            try:
                cfg = yaml.safe_load(ymlfile)
            except yaml.YAMLError as exc:
                print("Error parsing configuration file")
                if hasattr(exc, 'problem_mark'):
                    mark = exc.problem_mark # pylint: disable=no-member
                    print(f"Config file does not seem to be correct YAML - \
                            error at line {mark.line}, column {mark.column}")
                sys.exit(1)
        if "meetup" not in cfg:
            print("Invalid configuration file")
            sys.exit(1)
        self.client_id = cfg['meetup']['client_id']
        self.client_secret = cfg['meetup']['client_secret']
        self.base_api_url = BASE_API_URL
        self.access_url = ACCESS_URL
        self.debug = DEBUG

        if cfg['meetup']['oauth_type'] and cfg['meetup']['oauth_type'] == 'anon':
            self.oauth_headers = self.get_oauth_token(cfg)

    def get_oauth_token(self, cfg):
        """
        Get an Oauth token
        """
        grant_type = 'anonymous_code'
        headers = {'Accept': 'application/json'}
        auth_params = {'client_id': self.client_id,
                       'response_type': grant_type,
                       'redirect_uri': cfg['meetup']['redirect_uri']}
        print("Attempting to authenticate against Meetup.com")
        try:
            auth_response = requests.get(cfg['meetup']['auth_url'],
                                         params=auth_params,
                                         headers=headers,
                                         timeout=30)
        except requests.exceptions.RequestException as error:
            raise SystemExit(error) from error
        auth_token = auth_response.json()["code"]
        # Request access token
        access_params = {'client_id': self.client_id,
                         'client_secret': self.client_secret,
                         'grant_type': grant_type,
                         'redirect_uri': cfg['meetup']['redirect_uri'],
                         'code': auth_token}
        try:
            access_response = requests.post(self.access_url,
                                            params=access_params,
                                            headers=headers,
                                            timeout=30)
        except requests.exceptions.RequestException as error:
            raise SystemExit(error) from error
        access_token = access_response.json()["access_token"]
        auth_string = f'bearer {access_token}'
        oauth_headers = {'Accept': 'application/json', 'Authorization': auth_string}
        return oauth_headers

    def refresh_token(self, refresh_token):
        """
        Refresh token
        """
        headers = {'Accept': 'application/json'}
        print("Attempting to refresh Meetup token")
        refresh_params = {'client_id': self.client_id,
                          'client_secret':self.client_secret,
                          'grant_type':'refresh_token',
                          'refresh_token':refresh_token}
        try:
            access_response = requests.post(self.access_url,
                                            params=refresh_params,
                                            headers=headers,
                                            timeout=30)
        except requests.exceptions.RequestException as error:
            raise SystemExit(error) from error
        access_token = access_response.json()["access_token"]
        auth_string = f'bearer {access_token}'
        oauth_headers = {'Accept': 'application/json', 'Authorization': auth_string}
        self.oauth_headers = oauth_headers

    def auth_jwt(self, jwt):
        """
        Get an Oauth token
        """
        headers = {'Accept': 'application/json'}
        auth_params = {'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
                       'assertion': jwt}
        print("Attempting to authenticate against Meetup.com")
        try:
            access_response = requests.post(self.access_url,
                                            params=auth_params,
                                            headers=headers,
                                            timeout=30)
        except requests.exceptions.RequestException as error:
            raise SystemExit(error) from error
        access_token = access_response.json()["access_token"]
        auth_string = f'bearer {access_token}'
        oauth_headers = {'Accept': 'application/json', 'Authorization': auth_string}
        self.oauth_headers = oauth_headers

    def graphql_query(self, query, variables):
        """
        Query the GraphQL API
        """
        res = requests.post(self.base_api_url,
                            json={'query': query, 'variables': variables},
                            headers=self.oauth_headers,
                            timeout=30)
        return res.json()

    def search_for_groups(self,
                          geonames_user,
                          city,
                          country,
                          radius,
                          search_string):
        """
        Search for groups
        """
        lat, lon = get_lat_lon(geonames_user, city, country)
        if all([lat, lon]):
            query = """query ($search_string: String!, $lat: Float!, $lon: Float!, $radius: Int!) {
                keywordSearch(filter: { query: $search_string, lat: $lat, lon: $lon, radius: $radius, source: GROUPS }) {
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
            }"""
            variables = f'{{"search_string": "{search_string}",\
                    "lat": {lat},\
                    "lon": {lon},\
                    "radius": {radius}}}'
            res = self.graphql_query(query, variables)
            ids = [x for y in [item['node'].values()
                               for item in res['data']['keywordSearch']['edges']]
                   for x in y]
            return ids
        return []

    def get_group(self, group_id):
        """
        Retrieve the group info
        """
        query = """query ($groupid: ID!) {
            group(id: $groupid) {
                name
                link
                city
                country
                memberships {
                    count 
                }
             }
          }"""
        variables = f'{{"groupid": "{group_id}"}}'
        res = self.graphql_query(query, variables)
        res['data']['group']['id'] = group_id
        res['data']['group']['members'] = res['data']['group']['memberships']['count']
        del res['data']['group']['memberships']
        return res['data']['group']

    def get_number_of_events(self, group_id):
        """
        Retrieve the number of events for a group
        """
        query = """query ($groupid: ID!) {
            group(id: $groupid) {
                pastEvents(input: {}) {
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
          }"""
        variables = f'{{"groupid": "{group_id}"}}'
        res = self.graphql_query(query, variables)
        return res['data']['group']['pastEvents']['count']

    def get_network_events(self, network_url):
        """
        Get events from a network
        """
        query = """query ($urlname: String!) {
            proNetworkByUrlname(urlname: $urlname) {
                eventsSearch(filter: { status: UPCOMING }, input: { first: 5 }) {
                    count
                    pageInfo {
                        endCursor
                    }
                    edges {
                        node {
                            id
                            title
                            eventUrl
                            dateTime
                            description
                            timezone
                        }
                    }
                }
            }
        }"""
        variables = f'{{"urlname": "{network_url}"}}'
        res = self.graphql_query(query, variables)
        return res['data']['proNetworkByUrlname']['eventsSearch']['edges']

    def get_network_groups(self, network_url):
        """
        Get events from a network
        """
        query = """query ($urlname: String!) {
            proNetworkByUrlname(urlname: $urlname) {
                groupsSearch(input: { first: 3 }) {
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
        }"""
        variables = f'{{"urlname": "{network_url}"}}'
        res = self.graphql_query(query, variables)
        return res

    def get_members(self, group_id):
        """
        Retrieve the members of a group
        """
        query = """query ($groupid: ID!) {
            group(id: $groupid) {
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
          }"""
        variables = f'{{"groupid": "{group_id}"}}'
        res = self.graphql_query(query, variables)
        return res

    def get_event_datetimes(self, group_id):
        """
        Get a list of datetimes for events
        """
        query = """query ($groupid: ID!) {
            group(id: $groupid) {
                pastEvents(input: {}) {
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
          }"""
        variables = f'{{"groupid": "{group_id}"}}'
        res = self.graphql_query(query, variables)
        datetime_strings = [x for y in [item['node'].values()
                                        for item in
                                        res['data']['group']['pastEvents']['edges']]
                            for x in y]
        # These are unicode strings so convert them to datetimes
        datetimes = []
        for dt_string in datetime_strings:
            # Use parse as strptime doesn't support TZ offsets
            date_time = parse(dt_string)
            datetimes.append(date_time)
        return datetimes

def filter_on_name(search_keys, groups):
    """
    Return a filtered set of groups based on name matching
    Meetup API search scope is full description not just name
    """
    name_matches = [group for group in groups
                    if any(key.lower() in group["name"].lower()
                           for key in search_keys)]
    return name_matches

def check_name_filter(search_keys, group):
    """
    Check a group against the search keys
    """
    for key in search_keys:
        if key.lower() in group["name"].lower():
            return True
    return False

def filter_on_members(filters, groups):
    """
    Return a filtered set of groups based on number of members
    """
    mem_filter = [group for group in groups
                  if group["members"] > filters['member_filter'][1]]
    return mem_filter

def filter_on_events(meetup, filters, groups, rate_limit):
    """
    Return a filtered set of groups based on minimum number of events
    """
    for group in groups:
        group["number_events"] = meetup.get_number_of_events(group['id'])
        time.sleep(rate_limit)
    num_event_filter = [group for group in groups
                        if group["number_events"] > filters['event_filter'][1]]
    return num_event_filter

def filter_on_period(meetup, filters, groups, rate_limit):
    """
    Return a filtered set of groups based on events in past configurable period
    """
    for group in groups:
        group["number_in_period"] = number_in_period(meetup.get_event_datetimes(group['id']),
                                                     filters['period_filter'][1])
        group["period"] = filters['period_filter'][1]
        time.sleep(rate_limit)
    period_event_filter = [group for group in groups
                           if group["number_in_period"]
                           > filters['period_filter'][2]]
    return period_event_filter

def filter_on_freq(meetup, filters, groups, rate_limit):
    """
    Return a filtered set based on a configurable past event frequency
    """
    for group in groups:
        datetimes = meetup.get_event_datetimes(group['id'])
        group["event_freq"] = event_frequency(datetimes)
        time.sleep(rate_limit)
    event_freq_filter = [group for group in groups
                         if group["event_freq"]
                         < filters['freq_filter'][1]]
    return event_freq_filter

def get_lat_lon(geonames_user, city, country):
    """
    Get a city's lat and lon using Geonames
    """
    try:
        geodata = geocoder.geonames(city, country=country, key=geonames_user)
    except requests.exceptions.RequestException as error:
        print("Could not connect to geocoding API - exiting")
        raise SystemExit(error) from error
    if geodata.ok:
        return geodata.lat, geodata.lng
    print(f"No Geocode results found for {city} {country}")
    return False, False
