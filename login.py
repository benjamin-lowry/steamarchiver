#!/usr/bin/env python3
import json
from steam.client import SteamClient
import steam.webauth as wa
from steam.enums import EResult
from os import makedirs
from os.path import exists, join
from datetime import datetime
from dateutil.relativedelta import relativedelta
import logging

def auto_login(client, username="", password="", fallback_anonymous=False, relogin=True):
    assert(type(client) == SteamClient)
    makedirs("./auth", exist_ok=True)
    
    _LOG = logging.getLogger("Login")
    webauth = wa.WebAuth()

    ## If we are not signing in and doing anonymous access
    if username == "anonymous":
        client.anonymous_login()
        return
    # If we have set a username and password in command line
    if username and password:
        keypath = join("./auth/", username + ".json")
        LOGON_DETAILS = {
			'username' : username,
			'password' : password,
        }
        try:
            webauth.login(**LOGON_DETAILS)
        except wa.TwoFactorCodeRequired:
            webauth.login(code=input("Enter your Steam Guard code (or simply press Enter if approved via app): "))
        except wa.EmailCodeRequired:
            webauth.login(code=input("Enter Email Code: "))
        
        # We are setting the auth file for refresh token storage
        if exists(keypath):
            with open(keypath) as f:
                credentials = json.load(f)
            # the Expiration Date field is required in order
            # to update the day before the Refresh Token expires
            expirationDate = datetime.strptime(credentials['expires'], "%Y-%m-%d %H:%M:%S.%f")
            dateNow = datetime.now()
            
            # If the username does not match the one on file, we need to make a new one
            if credentials['username'] != webauth.username:
                _LOG.info("New Username detected, updating credentials file")
                credentials = {
					'expires': (datetime.now() + relativedelta(months=6, days=-1)).strftime("%Y-%m-%d %H:%M:%S.%f"),
    				'username': webauth.username,
            		'refresh_token': webauth.refresh_token,
				}
                with open(keypath, 'w') as f:
                    json.dump(credentials, f, indent=4)
        else:
            _LOG.info("No credentials file detected, creating one")
            credentials = {
                'expires': (datetime.now() + relativedelta(months=6, days=-1)).strftime("%Y-%m-%d %H:%M:%S.%f"),
				'username': webauth.username,
                'refresh_token': webauth.refresh_token,
			}
            with open(keypath, 'w') as f:
                json.dump(credentials, f, indent=4)
                    
        print("Logging in as", webauth.username)
        client.login(webauth.username, access_token=webauth.refresh_token)
        with open("./auth/lastuser.txt", "w") as f: f.write(webauth.username)
        return
    if not username and exists("./auth/lastuser.txt") and relogin:
        _LOG.info("No username specified, attempting to login using saved login key")
        with open("./auth/lastuser.txt", "r") as f: username = f.read()
        keypath = join("./auth/", username + ".json")
        with open(keypath, "r") as f: credentials = json.load(f)
        print("Logging in as last user", credentials['username'], "using saved login key")
        client.login(credentials['username'], access_token=credentials['refresh_token'])
        return
    if username and exists(join("./auth/", username + ".json")):
        _LOG.info("Attempting to login using saved login key for " + username)
        keypath = join("./auth/", username + ".json")
        with open(keypath, "r") as f: credentials = json.load(f)
        print("Logging in as", credentials['username'], "using saved login key")
        client.login(credentials['username'], access_token=credentials['refresh_token'])
        return
    # if no username, fall back to either anonymous or CLI login based on fallback_anonymous
    if fallback_anonymous:
        client.anonymous_login()
        return
    else:
        webauth.cli_login(username if username else input("Steam username: "))
        credentials = {
            'expires': (datetime.now() + relativedelta(months=6, days=-1)).strftime("%Y-%m-%d %H:%M:%S.%f"),
			'username': webauth.username,
            'refresh_token': webauth.refresh_token,
		}
        keypath = join("./auth/", webauth.username + ".json")
        with open(keypath, 'w') as f: json.dump(credentials, f, indent=4)
        client.login(webauth.username, access_token=webauth.refresh_token)
        with open("./auth/lastuser.txt", "w") as f: f.write(webauth.username)
        return

if __name__ == "__main__":
    auto_login(SteamClient(), fallback_anonymous=False, relogin=False)
