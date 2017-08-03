#!/usr/bin/env python
"""
Query meetup.com API
"""

import sys
import time
import meetup.api
import yaml
from prettytable import PrettyTable

def event_frequency(events):
    """
    Given a set of events calculate the average frequency of events in days
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
    Given a set of events calculate the number of events within a period
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

class MSMeetup(object):
    """
    Define class object
    """
    def __init__(self, configfile):
        with open(configfile, 'r') as ymlfile:
            cfg = yaml.load(ymlfile)
        self.api_key = cfg['meetup']['api_key']
        self.search_keys = cfg['meetup']['search_keys']
        self.name_filter = cfg['meetup']['name_filter']
        self.member_filter = (cfg['meetup']['member_filter'], cfg['meetup']['min_members'])
        self.event_filter = (cfg['meetup']['event_filter'], cfg['meetup']['min_events'])
        self.freq_filter = (cfg['meetup']['freq_filter'], cfg['meetup']['min_freq'])
        self.locations = {}
        # Horrible nested for loop which I can't quite work out how to fix
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
            group_info = con.GetFindGroups({'text':search_string,
                                            'country':country,
                                            'location':city})
        except:
            print 'Could not search for groups'
            sys.exit(1)
        if self.name_filter:
            group_info = self.filter_on_name(group_info)
        if self.member_filter[0]:
            group_info = self.filter_on_members(group_info)
        if self.event_filter[0]:
            group_info = self.filter_on_events(group_info)
        if self.freq_filter[0]:
            group_info = self.filter_on_freq(group_info)
        return group_info

    def get_past_events(self, group):
        """
        Get past events for a group
        """
        con = self.connect_to_meetup()
        res = con.GetEvents({'group_id': group.id,
                             'group_urlname': group.urlname,
                             'status': 'past'})
        return res.results

    def filter_on_name(self, groups):
        """
        Return a filtered set based on name matching
        """
        name_matches = [group for group in groups
                        if any(key.lower() in group.name.lower() for key in self.search_keys)]
        return name_matches

    def filter_on_members(self, groups):
        """
        Return a filtered set based on number of members
        """
        mem_filter = [group for group in groups if group.members > self.member_filter[1]]
        return mem_filter

    def filter_on_events(self, groups):
        """
        Return a filtered set based on minimum number of events
        """
        num_event_filter = [group for group in groups
                            if len(self.get_past_events(group)) > self.event_filter[1]]
        return num_event_filter

    def filter_on_freq(self, groups):
        """
        Return a filtered set based on a configurable past event frequency
        """
        event_freq_filter = [group for group in groups
                             if event_frequency(self.get_past_events(group)) < self.freq_filter[1]]
        return event_freq_filter

def main():
    """
    Main execution
    """
    configfile = 'config.yml'
    meetup_query = MSMeetup(configfile)
    table = PrettyTable(['Name', 'Members', 'City', 'Country', 'URL'])
    for city, country in meetup_query.locations.iteritems():
        res = meetup_query.search_via_api(city, country)
        for group in res:
            table.add_row([group.name, group.members, city, country, group.link])
    print table

if __name__ == "__main__":
    main()
