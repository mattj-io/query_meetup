#!/usr/bin/env python
"""
Query meetup.com API
"""

import sys
import time
import argparse
import meetup.api
import yaml
import xlsxwriter
from prettytable import PrettyTable

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
    if not name.endswith('.xlxs'):
        name = name+".xlsx"
    workbook = xlsxwriter.Workbook(name)
    row_count = {}
    col_widths = {}
    for group in groups:
        organizer_url = group.link+"members/"+str(group.organizer['id'])
        data = [group.name,
                group.members,
                group.city,
                group.country,
                group.link,
                group.organizer['name'],
                organizer_url]
        current_sheet = workbook.get_worksheet_by_name(group.country)
        if not current_sheet:
            current_sheet = workbook.add_worksheet(group.country)
            # Set the values for initial column widths from the column headings length
            col_widths[group.country] = add_columns(workbook, current_sheet, columns)
            row_count[group.country] = 0
        col = 0
        for item in data:
            # Update the column widths dictionary as we iterate through
            if len(str(item)) > col_widths[group.country][col]:
                col_widths[group.country][col] = len(str(item))
            current_sheet.write(row_count[group.country] + 1, col, item)
            col += 1
        row_count[group.country] += 1
    # Set column widths to display properly
    for sheet, values in col_widths.iteritems():
        current_sheet = workbook.get_worksheet_by_name(sheet)
        for col, value in values.iteritems():
            current_sheet.set_column(col, col, value + 1)
    workbook.close()

def add_columns(workbook, worksheet, columns):
    """
    Add columns to a worksheet
    """
    bold = workbook.add_format({'bold': True})
    col = 0
    col_widths = {}
    for item in columns:
        worksheet.write(0, col, item, bold)
        col_widths[col] = len(str(item))
        col += 1
    return col_widths

def create_table(columns, groups):
    """
    Create a table from a set of groups and column headers
    """
    table = PrettyTable(columns)
    for group in groups:
        organizer_url = group.link+"members/"+str(group.organizer['id'])
        data = [group.name,
                group.members,
                group.city,
                group.country,
                group.link,
                group.organizer['name'],
                organizer_url]
        table.add_row(data)
    return table

class MSMeetup(object):
    """
    Define class object and load config
    """
    def __init__(self, configfile):
        with open(configfile, 'r') as ymlfile:
            cfg = yaml.load(ymlfile)
        self.api_key = cfg['meetup']['api_key']
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

    def connect_to_meetup(self):
        """
        Connect to Meetup API
        """
        try:
            client = meetup.api.Client(self.api_key)
        except meetup.exceptions.ApiKeyError, err:
            print 'Could not connect to Meetup.com', err
            sys.exit(1)
        return client

    def search_via_api(self, city, country):
        """
        Do a search
        """
        con = self.connect_to_meetup()
        try:
            search_string = ' OR '.join(self.search_keys)
            group_info = con.GetFindGroups({'text':search_string, # pylint: disable=no-member
                                            'country':country,
                                            'location':city})
        except meetup.exceptions.MeetupBaseException as err:
            print 'Could not search for groups: %s' % err
            sys.exit(1)
        if self.filters['name_filter'][0]:
            group_info = self.filter_on_name(group_info)
        if self.filters['member_filter'][0]:
            group_info = self.filter_on_members(group_info)
        if self.filters['event_filter'][0]:
            group_info = self.filter_on_events(group_info)
        if self.filters['freq_filter'][0]:
            group_info = self.filter_on_freq(group_info)
        if self.filters['period_filter'][0]:
            group_info = self.filter_on_period(group_info)
        return group_info

    def get_member(self, member_id):
        """
        Retrieve a members details
        """
        con = self.connect_to_meetup()
        try:
            res = con.GetMember(member_id) # pylint: disable=no-member
        except meetup.exceptions.MeetupBaseException as err:
            print "Could not get member %s" % err
            sys.exit(1)
        return res

    def get_past_events(self, group):
        """
        Get past events for a group
        """
        con = self.connect_to_meetup()
        try:
            res = con.GetEvents({'group_id': group.id, # pylint: disable=no-member
                                 'group_urlname': group.urlname,
                                 'status': 'past'})
        except meetup.exceptions.MeetupBaseException as err:
            print "Could not get events %s" % err
            sys.exit(1)
        return res.results

    def filter_on_name(self, groups):
        """
        Return a filtered set of groups based on name matching
        Meetup API search scope is full description not just name
        """
        name_matches = [group for group in groups
                        if any(key.lower() in group.name.lower()
                               for key in self.search_keys)]
        return name_matches

    def filter_on_members(self, groups):
        """
        Return a filtered set of groups based on number of members
        """
        mem_filter = [group for group in groups
                      if group.members > self.filters['member_filter'][1]]
        return mem_filter

    def filter_on_events(self, groups):
        """
        Return a filtered set of groups based on minimum number of events
        """
        num_event_filter = [group for group in groups
                            if len(self.get_past_events(group)) > self.filters['event_filter'][1]]
        return num_event_filter

    def filter_on_period(self, groups):
        """
        Return a filtered set of groups based on events in past configurable period
        """
        period_event_filter = [group for group in groups
                               if number_in_period(group, self.filters['period_filter'][1])
                               > self.filters['period_filter'][2]]
        return period_event_filter

    def filter_on_freq(self, groups):
        """
        Return a filtered set based on a configurable past event frequency
        """
        event_freq_filter = [group for group in groups
                             if event_frequency(self.get_past_events(group))
                             < self.filters['freq_filter'][1]]
        return event_freq_filter

def main():
    """
    Main execution
    """
    parser = argparse.ArgumentParser(description='Query Meetup.com')
    parser.add_argument('--config', action="store", dest="config", help='configuration file to use')
    args = parser.parse_args()

    meetup_query = MSMeetup(args.config)
    columns = ['Name', 'Members', 'City', 'Country', 'URL', 'Organizer Name', 'Organizer URL']

    res = []
    for city, country in meetup_query.locations.iteritems():
        res += meetup_query.search_via_api(city, country)

    if 'xlsx' in meetup_query.outputs:
        create_spreadsheet(meetup_query.sheet_name, columns, res)
    if 'table' in meetup_query.outputs:
        table = create_table(columns, res)
        print table

if __name__ == "__main__":
    main()
