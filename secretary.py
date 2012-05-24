import smtplib
from email.mime.text import MIMEText
from contextlib import closing
import yaml
import random
import xmlrpclib
from datetime import date, datetime, timedelta
import re
import os

DATE_FMT = "%A %d %B"
TRAC_USR = "robosecretary"
TRAC_PSS = "iamrobot"
TRAC_URL = "intrac.flymine.org"
WIKI_PAGE = "WeeklyMeetingAgenda"
ROTA_PAGE = "WeeklyMeetingRota"
TODAY      = date.today()
DIR = os.path.dirname(__file__)

class StaffMember(object):
    def __init__(self, name, email):
        self.name = name
        self.email = email

class MeetingState(object):
    def __init__(self, tracserver):
        self.trac = tracserver
        self.rota = intrac.wiki.getPage(ROTA_PAGE)
        self.sequence = []
        for line in self.rota.split("\n"):
            m = re.search("^ - \w+ \d+ \w+: (.*)", line)
            if m:
                self.sequence.append(m.groups()[0])

        f = open(DIR + "/data/participants.yaml", "r")
        self.staff = yaml.load(f.read())
        f.close()

    def update_rota(self, next_meeting_date):
        new_rota = []
        for line in self.rota.split("\n"):
            if line.startswith("Chairs:"):
                new_rota.append(line)
                delta = timedelta(0)
                for name in self.sequence:
                    my_date = next_meeting_date + delta
                    new_rota.append(" - {0}: {1}".format(my_date.strftime(DATE_FMT), name))
                    delta = delta + timedelta(7)
            elif not re.search("^ - \w+ \d+ \w+:", line):
                new_rota.append(line)
        try:
            self.trac.wiki.putPage(ROTA_PAGE, "\n".join(new_rota), {"comment": "Automated update"})
        except Exception as e:
            if not re.search("not modified", str(e)):
                raise

    @property
    def chair(self):
        return self.staff_member(0)

    @property
    def next_chair(self):
        return self.staff_member(1)

    def staff_member(self, index):
        return StaffMember(self.sequence[index], self.staff[self.sequence[index]])

    def advance(self):
        head = self.sequence[0]
        tail = self.sequence[1:]
        self.sequence = tail + [head]


def update_agenda(trac, last_agenda, meeting):
    new_lines = []
    last_meeting_date = ""

    for line in last_agenda.split("\n"):
        m = re.search("Next meeting: (.*)", line)
        if m:
            last_meeting_date = m.groups()[0]
            timestr = "%s %d" % (last_meeting_date, TODAY.year)
            dt = datetime.strptime(timestr, "%A %d %B %Y")
            nextdate = dt + timedelta(7)
            new_lines.append(nextdate.strftime("Next meeting: " + DATE_FMT))
        elif line.startswith("Next Chair:"):
            new_lines.append("Next Chair: %s" % meeting.next_chair.name)
        else:
            new_lines.append(line)

        if line.startswith("Agenda:"):
            new_lines.extend([
                " - Add items here!",
                "",
                ("Agenda for %s:" % last_meeting_date)
            ])

    new_page = "\n".join(new_lines)

    trac.wiki.putPage("WeeklyMeetingAgenda", new_page, {"comment": "Automated update"})
    return new_page

def get_date_from_wiki(page):
    for line in page.split("\n"):
        m = re.search("Next meeting: (.*)", line)
        if m:
            last_meeting_date = m.groups()[0]
            timestr = "%s %d" % (last_meeting_date, TODAY.year)
            dt = datetime.strptime(timestr, "%A %d %B %Y")
            return date(dt.year, dt.month, dt.day)

def get_this_weeks_items(page):
    relevants = []
    relevant = False
    for line in page.split("\n"):
        if line.startswith("Agenda:"):
            relevant = True
        elif re.search("^[^\s]", line):
            relevant = False

        if relevant:
            relevants.append(line)

    return "\n".join(relevants)

def inform_everybody(agenda, chair, next_chair, current_meeting_date):
    delta = (current_meeting_date - TODAY)
    with open(DIR + "/data/message.text", "r") as fp:
        text = fp.read()
        msg = MIMEText(text.format(
            current_meeting_date.strftime(DATE_FMT),
            chair.name, next_chair.name, get_this_weeks_items(agenda)))

    me = "robo.secretary@intermine.org"
    you = "all@flymine.org"

    when = "tomorrow" if (delta.days == 1) else current_meeting_date.strftime('for ' + DATE_FMT)

    msg['Subject'] = 'Weekly Meeting %s' % when
    msg['From'] = me
    msg['To'] = you

    print msg.as_string()
    s = smtplib.SMTP('ppsw.cam.ac.uk')
    try:
        s.sendmail(me, [you, chair.email, next_chair.email], msg.as_string())
    except e:
        print "Sending failed: %s" % e
    s.quit()

if __name__ == "__main__":
    intrac = xmlrpclib.ServerProxy(
        "http://{0}:{1}@{2}/login/xmlrpc".format(TRAC_USR, TRAC_PSS, TRAC_URL))
    agenda = intrac.wiki.getPage(WIKI_PAGE)

    meeting = MeetingState(intrac)

    current_meeting_date = get_date_from_wiki(agenda)
    if TODAY >= current_meeting_date:
        agenda = update_agenda(intrac, agenda, meeting)
        current_meeting_date = get_date_from_wiki(agenda)
        meeting.advance()

    meeting.update_rota(current_meeting_date)

    chair = meeting.chair
    next_chair = meeting.next_chair

    # Send emails on the day before as reminder, or on the day as update.
    delta = (current_meeting_date - TODAY)
    if (delta.days == 1) or (delta.days == 0):
        inform_everybody(agenda, chair, next_chair, current_meeting_date)
