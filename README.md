# Query tool for Meetup.com

This tool queries the Meetup.com API on multiple search terms and using multiple filters on the results

## Requirements:

It currently has the following dependencies, all available via pip

```
requests
prettytable
pyyaml
xlsxwriter
```

You can also add these dependancies by installing virtualenv:
1. `pip install virtualenv`
1. `mkdir venv`
1. `virtualenv venv`
1. `source venv/bin/activate`
1. `cd query_meetup`
1. `pip install -r requirements.txt`

Meetup.com uses Oauth2 for authentication and authorization, in order to use this script you'll need to have set up an Oauth Consumer on your Meetup.com account. Once that is set up, you'll need to add the Key, Secret and Redirect URI into the configuration file, along with your Meetup.com email and password. The Redirect URI isn't actually used for anything, but is required as part of the Oauth process.

### Configuration

The script takes a single argument --config which requires a path to your yaml config file as described below. An example YAML file is included

```
query_meetup.py --config matt_test.yml
```

### Config file syntax

```
meetup:
    client_id: YOUR_MEETUP_CLIENT_ID
    client_secret: YOUR_MEETUP_CLIENT_SECRET
    email: YOUR_MEETUP_EMAIL
    password: YOUR_MEETUP_PASSWORD
    redirect_uri: YOUR_REDIRECT_URI
    base_api_url: https://api.meetup.com
    auth_url: https://secure.meetup.com/oauth2/authorize
    access_url: https://secure.meetup.com/oauth2/access
    oauth_url:  https://api.meetup.com/sessions
    radius: 5
    name_filter: True
    member_filter: True
    event_filter: True
    freq_filter: False
    period_filter: False
    period: 12
    period_min: 4
    min_members: 300
    min_events: 4
    min_freq: 60
    search_keys:
        - openstack
        - mesos
        - docker
        - data science
        - kubernetes
        - flink
        - spark
        - microservices
        - cloud native
        - big data
        - cassandra
        - kafka
        - scala
        - hadoop
        - coreos
        - software circus
        - data engineering
        - devops
locations:
    UK:
        - Manchester
        - Bristol
        - London
        - Birmingham
    DE:
        - Hamburg
        - Berlin
output:
    types:
         - table
         - xlsx
    sheet_name: test.xlsx
```                

client_id - the key for your Oauth Consumer

client_secret - the secret for your Oauth Consumer

email - the email registered with Meetup.com account

password - the password for your Meetup.com account

redirect_uri - the Redirect URI that you registered for your Oauth Consumer

radius - radius around the search cities

name_filter - apply the defined search keys as a second pass against the actual name of a set of groups. Meetup.com's search API does full text search of body descriptions as well, so returns a lot of results. This gives a further element of specifity. Boolean.

member_filter - use the number of members filter. Boolean.

min_members - the minimum number of members the member filter will look for.

event_filter - use the number of events filter. Boolean.

min_events - the minimum number of events a returned group should have. This looks for past events over the entire life of the group.

freq_filter - use the frequency of events filter. Boolean

min_freq - the minimum frequency of events, counted as average days between events.

period_filter - use the period filter. Boolean.

period - period of time for the period filter in months. This is back from current date.

min_period - the minimum number of events that should have occurred within the defined period.

search_keys - list of search keys to use to search for groups. These are currently concatenated with OR for the purposes of the query.

locations - the locations to query.

output

types  - output format. Spreadsheet and console table are supported

sheet_name - name of spreadsheet to create, this can be a full path

Spreadsheet output will create xlsx format, with a worksheet per country defined in your locations. Spreadsheet name can be defined in the config file as above.
