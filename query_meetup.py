#!/usr/bin/env python
"""
Query meetup.com API
"""

import requests
import sys
import os
import time
import argparse
import random
from collections import OrderedDict
import yaml
import xlsxwriter
from prettytable import PrettyTable
import json

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
    excluded = [ group for group in groups if group["country"] == country ]
    return excluded

def event_frequency(events):
    """
    Given a set of Meetup events calculate the average frequency of events in days
    """
    time_between = []
    # Meetup returns time in millisecond precision
    for i in range(0, len(events)-1, 1):
        # Get the difference between the next entry and convert to days
        diff = (events[i+1]['time'] - events[i]['time'])/86400000
        time_between.append(diff)
    average = sum(time_between)/len(time_between)
    return average

def number_in_period(events, period):
    """
    Given a set of Meetup events calculate the number of events within a period
    Not wildly accurate given seconds in month varies
    """
    count = 0
    # Assume period is in months, so convert to seconds
    time_start = time.time() - (period*2592000)
    for i in range(0, len(events), 1):
        # Meetup time in milliseconds so convert to seconds
        if events[i]['time']/1000 > time_start:
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
        group['organizer_url'] = group['link']+"members/"+str(group['organizer']['id'])
        group['organizer_name'] = group['organizer']['name']
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
        group['organizer_url'] = group['link']+"members/"+str(group['organizer']['id'])
        group['organizer_name'] = group['organizer']['name']
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
	self.oauth_url = cfg['meetup']['oauth_url']
	self.base_api_url = cfg['meetup']['base_api_url']
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
        redirect_uri='https://github.com/mattj-io/query_meetup'
        auth_params = { 'client_id': self.client_id, 'response_type': grant_type, 'redirect_uri': redirect_uri }
	print "Attempting to authenticate against Meetup.com"
        try:
	    auth_response = requests.get(self.auth_url, params=auth_params, headers=headers)
        except requests.exceptions.RequestException as e:
            raise SystemExit(e)
	auth_token = auth_response.json()["code"]
        # Request access token
        access_params = { 'client_id': self.client_id, 'client_secret': self.client_secret, 'grant_type': grant_type, 'redirect_uri': redirect_uri, 'code': auth_token }
        try:
	    access_response = requests.post(self.access_url, params=access_params, headers=headers)
        except requests.exceptions.RequestException as e:
            raise SystemExit(e)
        access_token = access_response.json()["access_token"]
        # Request oauth token
        access_token_string = 'Bearer %s' % access_token
        headers['Authorization'] = access_token_string
        oauth_params = { 'email': self.email, 'password': self.password }
        try:
	    oauth_response = requests.post(self.oauth_url, params=oauth_params, headers=headers)
        except requests.exceptions.RequestException as e:
            raise SystemExit(e)
	print "Successfully authenticated against Meetup.com"
        auth_string = 'Bearer %s' % oauth_response.json()["oauth_token"]
        oauth_headers = {'Accept': 'application/json', 'Authorization': auth_string}
	return oauth_headers

    def search_for_groups(self, city, country, oauth_headers):
        """
	Do a search
	"""
	api_url = self.base_api_url + "/find/groups"
	search_string = ' OR '.join(self.search_keys)
	params = { 'country': country, 'location': city, 'radius': self.radius, 'text': search_string }
	try:
	    res = requests.get(api_url, params=params, headers=oauth_headers)
	except requests.exceptions.RequestException as e:
            raise SystemExit(e)
        # Meetup sometimes gets the wrong country so filter them here
	excluded = exclude_by_country(res.json(), country)
	return excluded

    def get_member(self, member_id, oauth_headers):
        """
        Retrieve a members details
        """
        api_url = self.base_api_url + "/members/member_id"
        try:
            res = requests.get(api_url, headers=oauth_headers)
	except requests.exceptions.RequestException as e:
    	    raise SystemExit(e)
        return res.json()

    def get_past_events(self, group, oauth_headers):
        """
        Get past events for a group
        """
	api_url = self.base_api_url + "/%s/events" % group["urlname"]
	params = { 'status': 'past' }
        try:
	    res = requests.get(api_url, headers=oauth_headers, params=params)
        except requests.exceptions.RequestException as e:
            raise SystemExit(e)
        return res.json()

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

    def filter_on_events(self, groups, oauth_headers):
        """
        Return a filtered set of groups based on minimum number of events
        """
        for group in groups:
            group["number_events"] = len(self.get_past_events(group, oauth_headers))
	    time.sleep(self.api_rate_limit)
        num_event_filter = [group for group in groups
                            if group["number_events"] > self.filters['event_filter'][1]]
        return num_event_filter

    def filter_on_period(self, groups, oauth_headers):
        """
        Return a filtered set of groups based on events in past configurable period
        """
        for group in groups:
            group["number_in_period"] = number_in_period(self.get_past_events(group, oauth_headers),
                                                      self.filters['period_filter'][1])
            group["period"] = self.filters['period_filter'][1]
            time.sleep(self.api_rate_limit)
        period_event_filter = [group for group in groups
                               if group["number_in_period"]
                               > self.filters['period_filter'][2]]
        return period_event_filter

    def filter_on_freq(self, groups, oauth_headers):
        """
        Return a filtered set based on a configurable past event frequency
        """
        for group in groups:
            group["event_freq"] = event_frequency(self.get_past_events(group, oauth_headers))
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
                           ('URL', 'link'),
                           ('Organizer Name', 'organizer_name'),
                           ('Organizer URL', 'organizer_url')])

    res = []
	
    # Get Oauth token
    oauth_headers = meetup_query.get_oauth_token()
    for city, country in meetup_query.locations.iteritems():
        # Retry loop to handle API returning junk
        count = 0
        for count in range(0, 3):
            print "Searching for groups in City: %s Country: %s" % (city, country)
            res += meetup_query.search_for_groups(city, country, oauth_headers)
            if not res:
		print "No results for City: %s, Country: %s" % (city, country)
		time.sleep(meetup_query.api_rate_limit)
		break
            else:
		time.sleep(meetup_query.api_rate_limit)
                break
        else:
            print "Could not get result from API"
            sys.exit(1)
    print "Applying filters"
    if meetup_query.filters['name_filter'][0]:
        res = meetup_query.filter_on_name(res)
    if meetup_query.filters['member_filter'][0]:
        res = meetup_query.filter_on_members(res)
    if meetup_query.filters['event_filter'][0]:
        res = meetup_query.filter_on_events(res, oauth_headers)
        columns['Total Events'] = 'number_events'
    if meetup_query.filters['freq_filter'][0]:
        res = meetup_query.filter_on_freq(res, oauth_headers)
        columns['Frequency (days)'] = 'event_freq'
    if meetup_query.filters['period_filter'][0]:
        res = meetup_query.filter_on_period(res, oauth_headers)
        columns['Events in Period'] = 'number_in_period'
        columns['Period (months)'] = 'period'
    print "Deduplicating results"
    deduped = de_dupe(res)
    print "Creating output"
    if 'xlsx' in meetup_query.outputs:
        create_spreadsheet(meetup_query.sheet_name, columns, deduped)
    if 'table' in meetup_query.outputs:
       table = create_table(columns, deduped)
       print table

if __name__ == "__main__":
    main()
