from sqlalchemy import *
from sqlalchemy.pool import NullPool
from flask import Flask, request, render_template, g, redirect, Response
from flask import send_from_directory
import os, sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from flaskr import config, calls
import requests
import os
from datetime import datetime
import json
import psycopg2

app = Flask(__name__)

if config.sql_user == "" or config.api_key == "" or config.sql_password == "":
    print("Please add key, username, and password to config.py file before using this app.\n")
    exit()

DATABASEURI = "postgresql://" + config.sql_user + ":" + config.sql_password + "@35.243.220.243/proj1part2"
engine = create_engine(DATABASEURI)

# for profile icons
CURRENT_PATCH = "9.22.1/"
DATADRAGON_ENDPOINT = "http://ddragon.leagueoflegends.com/cdn/" + CURRENT_PATCH

# for SR Match History (END_IDX - BEGIN_IDX matches at a time pulled frmo api)
BEGIN_IDX = 0
END_IDX   = 20

def boolstr_to_int(s):
    return (int(s == 'true'))

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
    summoner_name = request.args.get('summonerName').casefold()
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
                       sid["name"].casefold(), sid["profileIconId"], sid["summonerLevel"],
                       sid["id"], sid["accountId"], sid["puuid"])
        icon_uri = DATADRAGON_ENDPOINT + "img/profileicon/" + str(sid["profileIconId"]) + ".png"
        return render_template("/profile.html", summoner_name=sid["name"], profile_icon=icon_uri, summoner_level=sid["summonerLevel"])
    else:
        icon_uri = DATADRAGON_ENDPOINT + "img/profileicon/" + str(results[1]) + ".png"
        cursor.close()
        return render_template("/profile.html", summoner_name=results[0], profile_icon=icon_uri, summoner_level=results[2])


@app.route('/tftMatchHistory', methods=['GET'])
def populate_tft_match_history():
    summoner_name = request.args.get('summonerName').casefold()
    icon = request.args.get('icon')
    lvl = request.args.get('lvl')
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
                        match["metadata"]["match_id"], name.casefold(), participant["placement"],
                        participant["last_round"], 1)
            # p = {'match_id': match["metadata"]["match_id"], 'summoner_name': name,
            #      'placement': participant["placement"], 'last_round': participant["last_round"], 'companion': 1}
            # p_all.append(p)
            # add to had_traits
            for trait in participant["traits"]:
                g.conn.execute('INSERT INTO had_traits VALUES (%s, %s, %s, %s, %s)',
                               match["metadata"]["match_id"], name.casefold(), trait["name"],
                               trait["tier_current"], trait["num_units"])
                # t = {'match_id': match["metadata"]["match_id"], 'summoner_name': name, 'name': trait["name"],
                #      'tier_current': trait["tier_current"], 'num_units': trait["num_units"]}
                # t_all.append(t)
            # add to used_tft_champ
            for unit in participant["units"]:
                g.conn.execute('INSERT INTO used_tft_champ VALUES (%s, %s, %s, %s, %s)',
                               match["metadata"]["match_id"], name.casefold(), unit["name"],
                               unit["tier"], unit["items"])
                # u = {'match_id': match["metadata"]["match_id"], 'summoner_name': unit["name"], 'tier': unit["tier"],
                #      'items': unit["items"]}
                # u_all.append(u)
    return render_template("profile.html", summoner_name=summoner_name, profile_icon=icon,
                           summoner_level=lvl)


@app.route('/srMatchHistory', methods=['GET'])
def populate_sr_match_history():
    summoner_name = request.args.get('summonerName').casefold()
    icon = request.args.get('icon')
    lvl = request.args.get('lvl')
    cursor = g.conn.execute('SELECT * FROM summoner WHERE summoner_name=%s', summoner_name)
    e_a_id = ''
    for x in cursor:
        e_a_id = x['encrypted_account_id']
    cursor.close()
    print("e_a_id: " + e_a_id)
    response = calls.get_sr_match_list(e_a_id, BEGIN_IDX, END_IDX)
    if response.status_code != 200:
        return render_template("/error.html")
    sid = response.json()
    matches = sid['matches']
    print("matches: ")
    print(matches)
    print()
    for match in matches:
        try:
            #print("match: ")
            #print(match)
            #print()
            game_id = match['gameId']

            #print("gameId: ")
            #print(game_id)
            #print()
            response = calls.get_sr_match(str(game_id))
            if response.status_code != 200:
                return render_template("/error.html")
            match_data = response.json()
            #print("match data: ")
            #print(match_data)
            #print()

            # TODO: game timestamps are longs in Riot API, ints in our database, may need to fix
            g.conn.execute('INSERT INTO sr_match VALUES (%s, %s, %s, %s) ON CONFLICT(match_id) DO NOTHING',
                            str(match_data['gameId']), match_data['gameCreation'],
                            match_data['gameDuration'], match_data['seasonId']);

            # add to ranked or normal as appropriate:
            queue_id = match_data['queueId']
            if (queue_id == 420 or queue_id == 440):  # ranked solo/duo, ranked flex
                g.conn.execute('INSERT INTO sr_ranked VALUES (%s) ON CONFLICT(match_id) DO NOTHING',
                               match_data['gameId'])
            else:  # normals
                g.conn.execute('INSERT INTO sr_normal VALUES (%s) ON CONFLICT(match_id) DO NOTHING',
                               match_data['gameId'])

            # add to team_plays_in:
            for team in match_data['teams']:
                win_int = -1
                if (team['win'] == 'Fail'):
                    win_int = 0
                else:
                    win_int = 1
                ban_list = '{ '
                for ban in team['bans']:
                    ban_list += (str(ban['championId']) + ',')
                # remove final comma, add closing brace:
                ban_list = ban_list[:-1] + '}'
                drag_int = boolstr_to_int(team['firstDragon'])
                inhib_int = boolstr_to_int(team['firstInhibitor'])

                g.conn.execute('INSERT INTO team_plays_in VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(match_id, team_id) DO NOTHING',
                                str(match_data['gameId']), str(team['teamId']),
                                str(win_int), ban_list, team['towerKills'], team['inhibitorKills'],
                                team['baronKills'], team['dragonKills'])

            # add to participant plays on:
            for participant in match_data['participants']:
                p_id = int(participant['participantId'])
                print(match_data['participantIdentities'][p_id-1]['player'])
                p_sid = match_data['participantIdentities'][p_id-1]['player']['summonerId']
                p_stats = participant['stats']
                g.conn.execute('INSERT INTO participant_plays_on VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(match_id, team_id, summoner_id) DO NOTHING',
                               str(match_data['gameId']), participant['teamId'], p_sid,
                               participant['championId'], participant['spell1Id'], participant['spell2Id'],
                               p_stats['visionScore'], p_stats['kills'], p_stats['assists'], p_stats['deaths'],
                               p_stats['champLevel'], p_stats['goldEarned'], p_stats['totalMinionsKilled'],
                               p_stats['totalDamageDealtToChampions'])
        except KeyError as e:
            print(e)
    return render_template("profile.html", summoner_name=summoner_name, profile_icon=icon,
                           summoner_level=lvl)



@app.route('/tftMatchHistory/show', methods=['GET'])
def display_tft_match_history():
    summoner_name = request.args.get('summonerName').casefold()
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


@app.route('/srMatchHistory/show', methods=['GET'])
def display_sr_match_history():
    summoner_name = request.args.get('summonerName').casefold()
    cursor = g.conn.execute('SELECT * FROM summoner WHERE summoner_name=%s', summoner_name)
    e_sid = ""
    for x in cursor:
        e_sid = x['encrypted_summoner_id']
    cursor = g.conn.execute('SELECT * FROM participant_plays_on WHERE summoner_id=%s', e_sid)
    team = []
    champion = []
    kda = []
    cs = []
    gold = []
    damage = []
    result = []
    for x in cursor:
        team_str = ""
        if int(x['team_id']) == 100:
            team_str = "Blue"
        else:
            team_str = "Red"
        team.insert(0, team_str)
        champion.insert(0, x['champion_id'])
        kills = x['kills']
        deaths = x['deaths']
        assists = x['assists']
        kda_str = str(kills) + "/" + str(deaths) + "/" + str(assists)
        kda.insert(0, kda_str)
        cs.insert(0, x['total_minions_killed'])
        gold.insert(0, x['gold_earned'])
        damage.insert(0, x['total_damage_dealt_to_champions'])

        cursor2 = g.conn.execute('SELECT * FROM team_plays_in WHERE match_id=%s AND team_id=%s',
                                 x['match_id'], x['team_id'])
        win_str = ""
        for y in cursor2:
            if int(y['win']) == 1:
                win_str = "Win"
            else:
                win_str = "Loss"
        result.insert(0, win_str)

    matches = [{"team": t, "champ": c, "kda": k, "cs": s, "gold": g, "damage": d, "result": r}
               for t, c, k, s, g, d, r in zip(team, champion, kda, cs, gold, damage, result)]

    context = dict(data=matches)

    cursor.close()
    cursor2.close()

    return render_template("srmatchhistory.html", **context, summoner_name=summoner_name)


@app.route('/analyzeSr', methods=['GET'])
def analyze_sr_match_history():
    summoner_name = request.args.get('summonerName').casefold()
    cursor = g.conn.execute('SELECT * FROM summoner WHERE summoner_name=%s', summoner_name)
    e_sid = ""
    for x in cursor:
        e_sid = x['encrypted_summoner_id']
    wins = 0
    k = 0
    d = 0
    a = 0
    cs = 0
    damage = 0
    gold = 0
    cursor = g.conn.execute('SELECT * FROM participant_plays_on WHERE summoner_id=%s', e_sid)
    count = 0
    for x in cursor:
        k += x['kills']
        a += x['assists']
        d += x['deaths']
        cs += x['total_minions_killed']
        damage += x['total_damage_dealt_to_champions']
        gold += x['gold_earned']

        cursor2 = g.conn.execute('SELECT * FROM team_plays_in WHERE match_id=%s AND team_id=%s',
                                 x['match_id'], x['team_id'])
        for y in cursor2:
            wins += int(y['win'])
        
        count += 1

    cursor.close()
    cursor2.close()

    # protect against divide by 0:
    if (count <= 0 ):
        count = 1

    win_rate = float(wins/count)
    k_avg = float(k/count)
    d_avg = float(d/count)
    a_avg = float(a/count)
    cs_avg = float(cs/count)
    damage_avg = float(damage/count)
    gold_avg = float(gold/count)
    kda = str(k_avg) + "/" + str(d_avg) + "/" + str(a_avg)

    return render_template("sranalysis.html", 
                           win_rate=str(win_rate), 
                           kda=kda,
                           cs_avg=str(cs_avg),
                           damage_avg=str(damage_avg),
                           gold_avg=str(gold_avg),
                           summoner_name=summoner_name)


@app.route('/analyzeTft', methods=['GET'])
def analyze_tft_match_history():
    summoner_name = request.args.get('summonerName').casefold()
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
    cursor.close()
    # protect against divide by 0
    if (i <= 0):
        i = 1

    avg_place /= i
    avg_last_round /= i
    print(float(avg_place))
    return render_template("tftanalysis.html", avg_place=str(avg_place), avg_last_round=str(avg_last_round),
                           summoner_name=summoner_name, profile_icon=icon, summoner_level=lvl)


@app.route('/favicon.ico')
def favicon(): 
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')


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
    cursor.close()
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
    cursor.close()
    return render_template("champions.html", **context, summoner_name=summoner_name, profile_icon=icon, summoner_level=lvl)


# deletes current summoner if it exists and inserts new (potentially updated values)
def add_summoner(s_id, s_type):
    response = null
    if s_type == "puuid":
        response = calls.get_summoner_by_puuid(s_id)
    elif s_type == "encrypted_summoner_id":
        response = calls.get_summoner_by_encrypted_summoner_id(s_id)
    elif s_type == "summoner_name":
        response = calls.get_summoner_info(s_id)
    sid = response.json()
    g.conn.execute('DELETE FROM summoner WHERE summoner_name=%s', sid["name"])
    g.conn.execute('INSERT INTO summoner VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING',
                   sid["name"].casefold(), sid["profileIconId"], sid["summonerLevel"],
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
    cursor.close()
    return render_template("champions.html", **context)


@app.route('/callSrQuery', methods=['GET'])
def callChampQuery():
    return render_template("srmatches.html")


@app.route('/srQuery', methods=['POST'])
def srQuery():
    summoner_name = request.form.get('summoner_name')
    cursor = g.conn.execute('SELECT * FROM summoner WHERE summoner_name=%s', summoner_name)
    s_id = ""
    for x in cursor:
        s_id = x['encrypted_summoner_id']
    cs = request.form.get('cs')
    gold_earned = request.form.get('gold_earned')
    champ_level = request.form.get('champ_level')
    print(s_id + " " + cs + " " + gold_earned + " " + champ_level)
    if s_id == "":
        cursor = g.conn.execute('SELECT DISTINCT team_plays_in.win, participant_plays_on.summoner_id, participant_plays_on.champion_id, participant_plays_on.kills, participant_plays_on.assists, participant_plays_on.deaths, participant_plays_on.champ_level, participant_plays_on.gold_earned, participant_plays_on.total_minions_killed FROM participant_plays_on, team_plays_in WHERE participant_plays_on.team_id=team_plays_in.team_id AND participant_plays_on.match_id=team_plays_in.match_id AND participant_plays_on.total_minions_killed>=%s AND participant_plays_on.gold_earned>=%s AND participant_plays_on.champ_level=%s;',
                                cs, gold_earned, champ_level)
    else:
        cursor = g.conn.execute('SELECT DISTINCT team_plays_in.win, participant_plays_on.summoner_id, participant_plays_on.champion_id, participant_plays_on.kills, participant_plays_on.assists, participant_plays_on.deaths, participant_plays_on.champ_level, participant_plays_on.gold_earned, participant_plays_on.total_minions_killed FROM participant_plays_on, team_plays_in WHERE participant_plays_on.team_id=team_plays_in.team_id AND participant_plays_on.match_id=team_plays_in.match_id AND participant_plays_on.summoner_id=%s AND participant_plays_on.total_minions_killed>=%s AND participant_plays_on.gold_earned>=%s AND participant_plays_on.champ_level=%s;',
                                s_id, cs, gold_earned, champ_level)
    s_id_ = []
    win = []
    champ_id_ = []
    cs_ = []
    gold_earned_ = []
    champ_level_ = []
    for x in cursor:
        print(x)
        win.append(x['win'])
        s_id_.append(x['summoner_id'])
        champ_id_.append(x['champion_id'])
        cs_.append(x['total_minions_killed'])
        gold_earned_.append(x['gold_earned'])
        champ_level_.append(x['champ_level'])
    cursor.close()
    for i in range(len(s_id_)):
        add_summoner(s_id_[i], "encrypted_summoner_id")
        cursor = g.conn.execute('SELECT * FROM summoner WHERE encrypted_summoner_id=%s', s_id_[i])
        for x in cursor:
            s_id_[i] = x['summoner_name']
        cursor.close()
    results = [{"champ_level": m, "gold_earned": o, "cs": p, "champion_id": q, "summoner_name": s, "win": t}
               for m, o, p, q, s, t in zip(champ_level_, gold_earned_, cs_, champ_id_, s_id_, win)]
    context = dict(data=results)
    return render_template("srmatches.html", **context)



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

