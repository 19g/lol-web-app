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

@app.before_request
def before_request():
    """
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


@app.route('/home')
@app.route('/index')
@app.route('/')
def home():
    return render_template("home.html")


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
    return render_template("profile.html", summoner_name=summoner_name)


@app.route('/tftMatchHistory/show', methods=['GET'])
def display_tft_match_history():
    summoner_name = request.args.get('summonerName')
    icon = request.args.get('icon')
    lvl = request.args.get('lvl')
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
    return render_template("tftmatchhistory.html", **context, summoner_name=summoner_name, profile_icon=icon,
                           summoner_level=lvl)


@app.route('/analyzeTft', methods=['GET'])
def analyze_tft_match_history():
    summoner_name = request.args.get('summonerName')
    icon = request.args.get('icon')
    lvl = request.args.get('lvl')
    print(summoner_name)
    cursor = g.conn.execute('SELECT * FROM participates_in_tft WHERE summoner_name=%s', summoner_name)
    avg_place = 0.0
    avg_last_round = 0.0
    i = 0.0
    for x in cursor:
        avg_place += float(x['placement'])
        avg_last_round += float(x['last_round'])
        print(float(avg_place))
        i += 1
    avg_place /= i
    avg_last_round /= i
    print(float(avg_place))
    return render_template("tftanalysis.html", avg_place=str(avg_place), avg_last_round=str(avg_last_round),
                           summoner_name=summoner_name, profile_icon=icon, summoner_level=lvl)


@app.route('/updateChamps', methods=['GET'])
def update_champ_list():
    summoner_name = request.args.get('summonerName')
    icon = request.args.get('icon')
    lvl = request.args.get('lvl')
    add_summoner(summoner_name, "summoner_name")
    cursor = g.conn.execute('SELECT * FROM summoner WHERE summoner_name=%s', summoner_name)
    s_id = ""
    for x in cursor:
        s_id = x['encrypted_summoner_id']
    response = calls.get_champion_masteries(s_id)
    sid = response.json()
    for i in range(len(sid)):
        g.conn.execute('INSERT INTO owns_champion VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING',
                       sid[i]["championId"], sid[i]["championLevel"], 0, summoner_name)
    update_ftp()
    return render_template("champions.html", summoner_name=summoner_name, profile_icon=icon, summoner_level=lvl)


# update list of free to play champions
def update_ftp():
    response = calls.get_free_champions()
    sid = response.json()
    i = 0
    res = -1
    for champ in sid:
        if champ[i] == 'f':
            res = 0
        elif champ[i] == 't':
            res = 1
        g.conn.execute('UPDATE owns_champion SET free_to_play=1 WHERE champion_id=%s', res)
        i += 1
    return


@app.route('/champAnalysis', methods=['GET'])
def showChamps():
    summoner_name = request.args.get('summonerName')
    icon = request.args.get('icon')
    lvl = request.args.get('lvl')
    cursor = g.conn.execute('SELECT champion_id, mastery, free_to_play FROM owns_champion WHERE summoner_name=%s', summoner_name)
    a = []
    for x in cursor:
        c = [x["champion_id"], x["mastery"], x["free_to_play"]]
        a.append(c)

    return render_template("champions.html", data=a, summoner_name=summoner_name, profile_icon=icon, summoner_level=lvl)


# deletes current summoner if it exists and inserts new (potentially updated values)
def add_summoner(s_id, s_type):
    response = null
    print("hey")
    print(s_id)
    if s_type == "puuid":
        response = calls.get_summoner_by_puuid(s_id)
    elif s_type == "encrypted_summoner_id":
        response = calls.get_summoner_by_encrypted_summoner_id(s_id)
    elif s_type == "summoner_name":
        response = calls.get_summoner_info(s_id)
    sid = response.json()
    print(sid["name"])
    g.conn.execute('DELETE FROM summoner WHERE summoner_name=%s', sid["name"])
    g.conn.execute('INSERT INTO summoner VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING',
                   sid["name"], sid["profileIconId"], sid["summonerLevel"],
                   sid["id"], sid["accountId"], sid["puuid"])
    return sid["name"]


@app.route('/champQuery', methods=['POST'])
def champQuery():
    mastery_min = request.form.get('mastery_min')
    mastery_max = request.form.get('mastery_max')
    c_id = request.form.get('champ_id')
    if mastery_max == "":
        mastery_max = 7
    if c_id == "":
        cursor = g.conn.execute('SELECT * FROM owns_champion WHERE mastery>=%s AND mastery<=%s', mastery_min, mastery_max)
    else:
        cursor = g.conn.execute('SELECT * FROM owns_champion WHERE mastery>=%s AND mastery<=%s AND champion_id=%s', mastery_min, mastery_max, c_id)
    champs = []
    masteries = []
    ftp = []
    for x in cursor:
        champs.append(x["champion_id"])
        masteries.append(x["mastery"])
        ftp.append(x["free_to_play"])
    results = [{"champion_id": m, "mastery": n, "free_to_play": o}
               for m, n, o in zip(champs, masteries, ftp)]
    context = dict(data=results)
    return render_template("champions.html", **context)


@app.route('/srQuery', methods=['POST'])
def srQuery():
    summoner_name = request.form.get('summoner_name')
    mastery_min = request.form.get('mastery_min')
    mastery_max = request.form.get('mastery_max')
    cs = request.form.get('cd')
    gold_earned = request.form.get('gold_earned')
    champ_level = request.form.get('champ_level')
    cursor = g.conn.execute('SELECT T.win, P.champion_id, P.kills, P.assists, P.deaths, P.champ_level, P.gold_earned, P.total_minions_killed FROM P participant_plays_on, T team_plays_in, C owns_champion WHERE C.mastery>=%s AND C.mastery<=%s AND P.cs>=%s AND P.gold_earned >=%s AND P.champ_level=%s',
                            mastery_min, mastery_max, cs, gold_earned, champ_level)



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
