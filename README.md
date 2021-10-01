# Query tool for Meetup.com

This tool was designed for the needs of Dev Rel teams looking for specific community groups to speak at all over the world. It queries the Meetup.com GraphQL API for a configurable set of locations with multiple keyword search terms and optional filters on the results.

If you need to find all the Java meetups with more than 100 members in Paris, or you want to find all the Cloud Native meetups in a bunch of cities in the US then you've found the right place.

Feature and pull requests welcome !

To use the Meetup API you need a Pro account unfortunately. 

## Requirements:

It currently has the following dependencies, all available via pip

```
requests
prettytable
pyyaml
xlsxwriter
geocoder
python-datutil
pytz
```

You can also add these dependancies by installing virtualenv:
1. `pip install virtualenv`
1. `mkdir venv`
1. `virtualenv venv`
1. `source venv/bin/activate`
1. `cd query_meetup`
1. `pip install -r requirements.txt`

Meetup.com uses Oauth2 for authentication and authorization, in order to use this script you'll need to have set up an Oauth Consumer on your Meetup.com account. Once that is set up, you'll need to add the Key, Secret and Redirect URI into the configuration file, along with your Meetup.com email and password. The Redirect URI isn't actually used for anything, but is required as part of the Oauth process.

The GraphQL API requires latitudes and longitudes as opposed to city names, so this is implemented using Geocoder. Currently only the Geonames provider is supported, but adding support for others would be trivial. To use the current code, you need to register at http://www.geonames.org/ and turn on the free webservices at http://www.geonames.org/manageaccount

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
    base_api_url: https://api.meetup.com/gql
    auth_url: https://secure.meetup.com/oauth2/authorize
    access_url: https://secure.meetup.com/oauth2/access
    oauth_url:  https://api.meetup.com/sessions
    geonames_user: YOURGEONAMES_USER
    api_rate_limit: 2
    radius: 25
    name_filter: True
    member_filter: True
    event_filter: True
    freq_filter: False
    period_filter: False
    period: 12
    period_min: 3
    min_members: 300
    min_events: 4
    min_freq: 60
    search_keys:
        - docker
        - kubernetes
        - microservices
        - cloud native
        - devops
    debug: False
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
    sheet_name: test
```                

client_id - the key for your Oauth Consumer

client_secret - the secret for your Oauth Consumer

email - the email registered with Meetup.com account

password - the password for your Meetup.com account

redirect_uri - the Redirect URI that you registered for your Oauth Consumer

geonames_user - the username to use for Geonames queries

api_rate_limit - number of seconds to wait between API queries

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

debug - output more detailed debugging info

locations - the locations to query. NOTE that if you are querying groups in Norway, you need to quote the country code ( 'NO' ) as NO is interpreted as False in YAML :)

output

types  - output format. Spreadsheet and console table are supported

sheet_name - name of spreadsheet to create, this can be a full path

Spreadsheet output will create xlsx format, with a worksheet per country defined in your locations. Spreadsheet name can be defined in the config file as above.
