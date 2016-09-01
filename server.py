import flask
from flask import Flask
from flask import render_template
from flask import request

from email.Parser import HeaderParser
import email.utils

from datetime import datetime
import re

import pygal
from pygal.style import Style

from IPy import IP
import geoip2.database

app = Flask(__name__)
reader = geoip2.database.Reader(
    '%s/data/GeoLite2-Country.mmdb' % app.static_folder)


@app.context_processor
def utility_processor():
    def getCountryForIP(line):
        ipv4_address = re.compile(r"""
            \b((?:25[0-5]|2[0-4]\d|1\d\d|[1-9]\d|\d)\.
            (?:25[0-5]|2[0-4]\d|1\d\d|[1-9]\d|\d)\.
            (?:25[0-5]|2[0-4]\d|1\d\d|[1-9]\d|\d)\.
            (?:25[0-5]|2[0-4]\d|1\d\d|[1-9]\d|\d))\b""", re.X)
        ip = ipv4_address.findall(line)
        if ip:
            ip = ip[0]  # take the 1st ip and ignore the rest
            if IP(ip).iptype() == 'PUBLIC':
                r = reader.country(ip).country
                if r:
                    return {
                        'iso_code': r.iso_code.lower(),
                        'country_name': r.name
                    }
    return dict(country=getCountryForIP)


@app.context_processor
def utility_processor():
    def duration(seconds, _maxweeks=99999999999):
        return ', '.join('%d %s' % (num, unit)
                         for num, unit in zip([(seconds // d) % m
                                               for d, m in ((604800, _maxweeks),
                                                            (86400, 7), (3600, 24),
                                                            (60, 60), (1, 60))],
                                              ['wk', 'd', 'hr', 'min', 'sec'])
                         if num)
    return dict(duration=duration)


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        data = request.form['headers'].strip()
        r = {}
        n = HeaderParser().parsestr(data)
        # graph = [['Hop', 'Delay', ]]
        graph = []
        c = len(n.get_all('Received'))
        for i in range(len(n.get_all('Received'))):
            line = n.get_all('Received')[i].split(';')
            try:
                next_line = n.get_all('Received')[i + 1].split(';')
            except IndexError:
                next_line = None
            org_time = email.utils.mktime_tz(
                email.utils.parsedate_tz(line[-1]))
            if not next_line:
                next_time = org_time
            else:
                next_time = email.utils.mktime_tz(
                    email.utils.parsedate_tz(next_line[-1]))

            if line[0].startswith('from'):
                data = re.findall(
                    'from\s+(.*?)\s+by(.*?)(?:(?:with|via)(.*?)(?:id|$)|id)', line[0], re.DOTALL)
            else:
                data = re.findall(
                    '()by(.*?)(?:(?:with|via)(.*?)(?:id|$)|id)', line[0], re.DOTALL)

            delay = org_time - next_time
            if delay < 0:
                delay = 0

            r[c] = {
                'Timestmp': org_time,
                'Time': datetime.fromtimestamp(org_time).strftime('%m/%d/%Y %I:%M:%S %p'),
                'Delay': delay,
                'Direction': map(lambda x: x.replace('\n', ' '), map(str.strip, data[0]))
            }
            c -= 1

        for i in r.values():
            if i['Direction'][0]:
                graph.append(["From: %s" % i['Direction'][0], i['Delay']])
            else:
                graph.append(["By: %s" % i['Direction'][1], i['Delay']])

        totalDelay = sum(map(lambda x: x['Delay'], r.values()))
        delayed = True if totalDelay else False

        custom_style = Style(
            background='transparent',
            plot_background='transparent',
        )
        line_chart = pygal.HorizontalBar(style=custom_style, height=200)
        line_chart.tooltip_fancy_mode = False
        line_chart.js = ['%s/js/pygal-tooltips.min.js' % app.static_url_path]
        line_chart.title = 'Total Delay is: %s' % utility_processor()['duration'](totalDelay)
        line_chart.x_title = 'Delay in seconds.'
        for i in graph:
            line_chart.add(i[0], i[1])
        chart = line_chart.render(is_unicode=True)

        summary = {
            'From': n.get('from'),
            'To': n.get('to'),
            'Cc': n.get('cc'),
            'Subject': n.get('Subject'),
            'MessageID': n.get('Message-ID'),
            'Date': n.get('Date'),
        }
        return render_template(
            'index.html', data=r, delayed=delayed, summary=summary,
            n=n, chart=chart)
    else:
        return render_template('index.html')


if __name__ == '__main__':
    app.debug = True
    app.run(host='127.0.0.1', port=8080)
