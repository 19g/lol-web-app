from sqlalchemy import *
from sqlalchemy.pool import NullPool
from flask import Flask, request, render_template, g, redirect, Response
from flaskr import config, calls
import requests
import os
from datetime import datetime
import json
import psycopg2

app = Flask(__name__)

DATABASEURI = "postgresql://" + config.sql_user + ":" + config.sql_password + "@35.243.220.243/proj1part2"
engine = create_engine(DATABASEURI)

# for profile icons
CURRENT_PATCH = "9.22.1/"
DATADRAGON_ENDPOINT = "http://ddragon.leagueoflegends.com/cdn/" + CURRENT_PATCH

#
# Example of running queries in your database
# Note that this will probably not work if you already have a table named 'test' in your database, containing meaningful data. This is only an example showing you how to run queries in your database using SQLAlchemy.
#
engine.execute("""CREATE TABLE IF NOT EXISTS test (
  id serial,
  name text
);""")
engine.execute("""INSERT INTO test(name) VALUES ('grace hopper'), ('alan turing'), ('ada lovelace');""")


@app.before_request
def before_request():
    """
     This function is run at the beginning of every web request
    (every time you enter an address in the web browser).
     We use it to setup a database connection that can be used throughout the request.

    The variable g is globally accessible.
    """
    try:
        g.conn = engine.connect()
    except:
        print("uh oh, problem connecting to database")
        import traceback;
        traceback.print_exc()
        g.conn = None


@app.teardown_request
def teardown_request(exception):
    try:
        g.conn.close()
    except Exception as e:
        print(e)
        pass


@app.route('/naw')
def index():
    """
  request is a special object that Flask provides to access web request information:

  request.method:   "GET" or "POST"
  request.form:     if the browser submitted a form, this contains the data in the form
  request.args:     dictionary of URL arguments, e.g., {a:1, b:2} for http://localhost?a=1&b=2

  See its API: http://flask.pocoo.org/docs/0.10/api/#incoming-request-data
  """

    # DEBUG: this is debugging code to see what request looks like
    print(request.args)

    cursor = g.conn.execute("SELECT name FROM test")
    names = []
    for result in cursor:
        names.append(result['name'])  # can also be accessed using result[0]
    cursor.close()

    context = dict(data=names)

    return render_template("index.html", **context)


@app.route('/home')
@app.route('/index')
@app.route('/')
def home():
    return render_template("home.html")


# Example of adding new data to the database
@app.route('/add', methods=['POST'])
def add():
    name = request.form['name']
    g.conn.execute('INSERT INTO test(name) VALUES (%s)', name)
    return redirect('/')


@app.route('/getSummoner', methods=['GET'])
def get_summoner():
    summoner_name = request.args.get('summonerName')
    # check if summoner name is already in database
    cursor = g.conn.execute('SELECT * FROM summoner WHERE summoner_name=%s', summoner_name)
    results = []
    for x in cursor:
        results.append(x['summoner_name'])
        results.append(x['profile_icon'])
        results.append(x['summoner_level'])
    # if not, add to database
    if len(results) == 0:
        cursor.close()
        response = calls.get_summoner_info(summoner_name)
        print(response.text)
        if response.status_code != 200:
            return render_template("/error.html")
        sid = response.json()
        g.conn.execute('INSERT INTO summoner VALUES (%s, %s, %s, %s, %s, %s)',
                       sid["name"], sid["profileIconId"], sid["summonerLevel"],
                       sid["id"], sid["accountId"], sid["puuid"])
        icon_uri = DATADRAGON_ENDPOINT + "img/profileicon/" + str(sid["profileIconId"]) + ".png"
        return render_template("/profile.html", summoner_name=sid["name"], profile_icon=icon_uri, summoner_level=sid["summonerLevel"])
    else:
        icon_uri = DATADRAGON_ENDPOINT + "img/profileicon/" + str(results[1]) + ".png"
        cursor.close()
        return render_template("/profile.html", summoner_name=results[0], profile_icon=icon_uri, summoner_level=results[2])


@app.route('/tftMatchHistory', methods=['GET'])
def populate_tft_match_history():
    summoner_name = request.args.get('summonerName')
    cursor = g.conn.execute('SELECT * FROM summoner WHERE summoner_name=%s', summoner_name)
    puuid = ''
    for x in cursor:
        puuid = x['puuid']
    cursor.close()
    response = calls.get_tft_match_list(puuid)
    if response.status_code != 200:
        return render_template("/error.html")
    sid = response.json()
    for i in sid:
        print("hello3")
        response = calls.get_tft_match(i)
        match = response.json()
        # add data to tft_match and either tft_normal or tft_ranked depending on queue id
        g.conn.execute('INSERT INTO tft_match VALUES (%s, %s) ON CONFLICT(match_id) DO NOTHING',
                        match["metadata"]["match_id"], match["info"]["game_datetime"])
        if match["info"]["queue_id"] == 1100:
            g.conn.execute('INSERT INTO tft_normal VALUES (%s)', match["metadata"]["match_id"])
        else:
            g.conn.execute('INSERT INTO tft_ranked VALUES (%s)', match["metadata"]["match_id"])
        # add to participates_in_tft
        p_all = []
        t_all = []
        u_all = []
        for participant in match["info"]["participants"]:
            print("hello1")
            # get summoner name
            name = add_summoner(participant["puuid"], "puuid")
            g.conn.execute('INSERT INTO participates_in_tft VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING',
                        match["metadata"]["match_id"], name, participant["placement"],
                        participant["last_round"], 1)
            # p = {'match_id': match["metadata"]["match_id"], 'summoner_name': name,
            #      'placement': participant["placement"], 'last_round': participant["last_round"], 'companion': 1}
            # p_all.append(p)
            # add to had_traits
            for trait in participant["traits"]:
                g.conn.execute('INSERT INTO had_traits VALUES (%s, %s, %s, %s, %s)',
                               match["metadata"]["match_id"], name, trait["name"],
                               trait["tier_current"], trait["num_units"])
                # t = {'match_id': match["metadata"]["match_id"], 'summoner_name': name, 'name': trait["name"],
                #      'tier_current': trait["tier_current"], 'num_units': trait["num_units"]}
                # t_all.append(t)
            # add to used_tft_champ
            for unit in participant["units"]:
                g.conn.execute('INSERT INTO used_tft_champ VALUES (%s, %s, %s, %s, %s)',
                               match["metadata"]["match_id"], name, unit["name"],
                               unit["tier"], unit["items"])
                # u = {'match_id': match["metadata"]["match_id"], 'summoner_name': unit["name"], 'tier': unit["tier"],
                #      'items': unit["items"]}
                # u_all.append(u)
    return render_template("profile.html")


@app.route('/tftMatchHistory/show', methods=['GET'])
def display_tft_match_history():
    summoner_name = request.args.get('summonerName')
    cursor = g.conn.execute('SELECT * FROM participates_in_tft WHERE summoner_name=%s', summoner_name)
    placement = []
    last_round = []
    companion = []
    game_datetime = []
    for x in cursor:
        placement.append(x['placement'])
        last_round.append(x['last_round'])
        companion.append(x['companion'])
        cursor2 = g.conn.execute('SELECT * FROM tft_match WHERE match_id=%s', x['match_id'])
        for y in cursor2:
            dt = int(y['game_datetime'])
            dt /= 1000
            game_datetime.append(datetime.utcfromtimestamp(dt).strftime('%Y-%m-%d %H:%M:%S'))
    matches = [{"placement": m, "last_round": n, "companion": o, "game_datetime": p}
               for m, n, o, p in zip(placement, last_round, companion, game_datetime)]
    cursor2.close()
    cursor.close()
    context = dict(data=matches)
    return render_template("tftmatchhistory.html", **context)


@app.route('/analyzeTft', methods=['GET'])
def analyze_tft_match_history():
    summoner_name = request.args.get('summonerName')
    cursor = g.conn.execute('SELECT * FROM participates_in_tft WHERE summoner_name=%s', summoner_name)
    avg_place = 0.0
    avg_last_round = 0.0
    i = 0.0
    for x in cursor:
        avg_place += x['placement']
        avg_last_round += x['last_round']
        i += 1.0
    avg_place /= i
    avg_last_round /= i
    return render_template("tftanalysis.html", avg_place=avg_place, avg_last_round=avg_last_round)


def analyze_tft(puuid):
    return render_template("tftmatchhistory.html", puuid)


def add_summoner(id, type):
    if type == "puuid":
        response = calls.get_summoner_by_puuid(id)
    sid = response.json()
    g.conn.execute('INSERT INTO summoner VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING',
                   sid["summoner_name"], sid["profileIconId"], sid["summonerLevel"],
                   sid["id"], sid["accountId"], sid["puuid"])
    return sid["summoner_name"]


if __name__ == "__main__":
    import click
    @click.command()
    @click.option('--debug', is_flag=True)
    @click.option('--threaded', is_flag=True)
    @click.argument('HOST', default='0.0.0.0')
    @click.argument('PORT', default=8111, type=int)
    def run(debug, threaded, host, port):
        print("running on %s:%d" % (host, port))
        app.jinja_env.auto_reload = True  # so we don't have to re-run file on every change
        app.config['TEMPLATES_AUTO_RELOAD'] = True
        app.run(host=host, port=port, debug=debug, threaded=threaded)
    run()
