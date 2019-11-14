import flaskr.config
import requests

# api url for north american server
endpoint_na1 = "https://na1.api.riotgames.com"
# tft endpoint for americas
endpoint_americas = "https://americas.api.riotgames.com"

# create a requests session
s = requests.Session()

# update headers for session with appropriate values
s.headers.update({"Accept-Charset": "application/x-www-form-url-encoded; charset=UTF-8",
                  "X-Riot-Token": flaskr.config.api_key,
                  "Accept-Language": "en-us"})


def get_free_champions():
    url = endpoint_na1 + "/lol/platform/v3/champion-rotations"
    response = s.get(url)
    return response


def get_summoner_info(summoner_name):
    url = endpoint_na1 + "/lol/summoner/v4/summoners/by-name/" + summoner_name
    response = s.get(url)
    return response


def get_champion_masteries(encrypted_summoner_id):
    url = endpoint_na1 + "/lol/champion-mastery/v4/champion-masteries/by-summoner/" + encrypted_summoner_id
    response = s.get(url)
    return response


def get_ranks(encrypted_summoner_id):
    url = endpoint_na1 + "/lol/league/v4/entries/by-summoner/" + encrypted_summoner_id
    response = s.get(url)
    return response.text


def get_sr_match_list(encrypted_account_id, begin_index, end_index):
    url = endpoint_na1 + "/lol/match/v4/matchlists/by-account/" + str(encrypted_account_id)
    url += "?endIndex=" + str(end_index) + "&beginIndex=" + str(begin_index)
    response = s.get(url)
    return response.text


def get_sr_match(game_id):
    url = endpoint_na1 + "/lol/match/v4/timelines/by-match/" + game_id
    response = s.get(url)
    return response.text


def get_tft_match_list(puuid):
    url = endpoint_americas + "/tft/match/v1/matches/by-puuid/" + str(puuid) + "/ids"
    response = s.get(url)
    return response.text


def get_tft_match(match_id):
    url = endpoint_americas + "/tft/match/v1/matches/" + str(match_id)
    response = s.get(url)
    return response.text
