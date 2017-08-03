First pass at Meetup querier

Requirements:

At the minute I haven't frozen it, so you will need to install the python dependencies, which are all available via pip

meetup.api

prettytable

pyyaml

An API key for Meetup.com, which you can find from the API link at the bottom of your Profile page

Takes a yaml config file eg.

```
meetup:
    api_key: 3425161f35704018433cb3a5f17a75
    name_filter: True
    member_filter: True
    event_filter: True
    freq_filter: False
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
         - table
```                

Meetup's search API does full text of body descriptions as well, so returns a lot of results that are probably not what we are looking for. This implements a second filter stage back on the name, which seems to return a better data set.

Configurable filters based on number of members, total number of events, and event frequency. 

Event frequency is an average in days between events

TODO implement file or spreadsheet output, implement CLI arguments as well as config file, freeze to binary, improve docs, improve ( add ) error checking 
