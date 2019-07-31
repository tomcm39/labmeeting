#mcandrew

import os
import sys
import re
import numpy as np
import pandas as pd

import argparse
import slack

import datetime

def listMembers():
    allMembers = client.users_list().data['members']
    id2memberName = {'id':[],'name':[]}
    for d in allMembers:
        if not d['is_bot']:
            id2memberName['id'].append(d['id'])
            id2memberName['name'].append(d['name'])
    return pd.DataFrame(id2memberName)

def listLabMeetingMembers():
    status,channels = client.channels_list(exclude_archived=1).data.items()
    if status[0] == "ok" and status[-1]:
        labMeetingInfo = [channel for channel in channels[-1] if channel['name']=='lab-meeting'][0] 
    members = pd.DataFrame({'id':labMeetingInfo['members']}) 
    return members

def grabHolidays(sem):
    from bs4 import BeautifulSoup
    import urllib
    year = int(re.findall('\d+',sem)[0])

    def lookForDaysOff(cols,signs):
        for sign in signs:
            if sign in cols[0].get_text().strip():
                return 1
        return 0

    def returnTargetedDate(row,targets):
        cols = row.find_all('td')
        if lookForDaysOff(cols,targets):
            date = ""
            for col in row.find_all('td'):
                contents = col.get_text().strip()
                
                if contents in months:
                    month = months[contents]
                    if month < 8:
                        date+="{:04d}-{:02d}-".format(year+1,month)
                    else:
                        date+="{:04d}-{:02d}-".format(year,month)
                elif contents in days:
                    date+="{:02d}".format(int(contents))
            return date
    

    months = {'January':1,'February':2,'March':3,'April':4,'May':5,'June':6,'July':7,'August':8,'September':9,'October':10,'November':11,'December':12}
    days = set([str(x) for x in np.arange(1,31+1)])
    
    htmlFile = urllib.request.urlopen('https://www.umass.edu/registrar/calendars/academic-calendar#{:s}'.format(sem)).read()
    soup = BeautifulSoup(htmlFile, 'html.parser')

    semsterHeader = soup.find_all('a',id=re.compile('{:s}'.format(sem)))[0]
    table = semsterHeader.find_next('table')
    
    holidays,firstLastDay = [],[]
    for row in table.find_all('tr'):
        date = returnTargetedDate(row,['Holiday','recess','Thanksgiving'])
        if date:
            holidays.append(date)

        date = returnTargetedDate(row,['First day of classes','Last day of final examinations'])
        if date:
            firstLastDay.append(date)
    return holidays,firstLastDay

def computeWeeksForLabMeeting(firstDay,lastDay,holidays,DOW):
    num2dow = {0:'M',1:'T',2:'W',3:'Th',4:'F',5:'Sa',6:'Su'}
    firstDay = datetime.datetime.strptime(firstDay,'%Y-%m-%d') 
    firstDOW = num2dow[firstDay.weekday()]

    lastDay = datetime.datetime.strptime(lastDay,'%Y-%m-%d')

    plus1Day = datetime.timedelta(days=1)
    while firstDOW != DOW:
        firstDay+=plus1Day
        firstDOW = num2dow[firstDay.weekday()]

    labMeetings = []
    labMeeting = firstDay
    holidays   = [datetime.datetime.strptime(x,'%Y-%m-%d') for x in holidays]
    plus7Days = datetime.timedelta(days=7)
    while labMeeting <= lastDay:
        if labMeeting in holidays:
            continue
        labMeetings.append(labMeeting)
        labMeeting+=plus7Days
    labMeetings = pd.DataFrame({'labMeetings':labMeetings})
    return labMeetings


def assignLabMeetings(labMembers,labMeetings):
    numLabMembers = len(labMembers)
    numMeetings = len(labMeetings)
    if numMeetings > numLabMembers:
        labMeetingsFirstAssigned = labMeetings.sample(numLabMembers).reset_index()
        labMeetingsFirstAssigned['members'] = labMembers.name

        remainingLabMeetings     = set(labMeetings.labMeetings) - set(labMeetingsFirstAssigned.labMeetings)
        remainingLabMeetings     = pd.DataFrame({'labMeetings':list(remainingLabMeetings)})
        numRemainingLabMeetings  = len(remainingLabMeetings)

        remainingLabMeetingMembers      = labMembers.sample(numRemainingLabMeetings)
        remainingLabMeetings['members'] = remainingLabMeetingMembers.reset_index().name
        
        labMeetings = labMeetingsFirstAssigned.append(remainingLabMeetings)
        labMeetings = labMeetings.drop(columns=['index'])

    else:
        labMeetingsFirstAssigned = labMeetings.sample(numLabMembers).reset_index()
        labMeetingsFirstAssigned['members'] = labMembers.name
        labMeetings = labMeetingsFirstAssigned
    return labMeetings.sort_values('labMeetings')


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument('--DOW',type=str,help='DOW is the day of week to hold lab meetings')
    parser.add_argument('--semester', type =str, help='The semester to randomize lab meeting. Format fall/springYYYY. Example = fall2019')
    args = parser.parse_args()

    DOW,semester = args.DOW, args.semester
    
    client = slack.WebClient(token=os.environ['SLACK_API_TOKEN'])
    allMembers = listMembers()
    members = listLabMeetingMembers()
    
    labMembers = members.merge(allMembers, on = ['id'], how='left')

    holidays,firstLastDay = grabHolidays('{:s}'.format(semester))
    firstDay,lastDay = firstLastDay

    labMeetings = computeWeeksForLabMeeting(firstDay,lastDay,holidays,DOW)
    labMeetings = assignLabMeetings(labMembers,labMeetings)

    now = datetime.datetime.now()
    labMeetings.to_csv('./labMeeting_sem={:s}_dow=={:s}_datetime={:s}.csv'.format(semester,DOW,now.isoformat()),index=False)
