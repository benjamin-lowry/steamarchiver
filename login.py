#!/usr/bin/env python3
from steam.client import SteamClient
from steam.enums import EResult
from os import makedirs
from os.path import exists

def auto_login(client, username="", password="", fallback_anonymous=True, relogin=True):
    assert(type(client) == SteamClient)
    makedirs("./auth", exist_ok=True)
    client.set_credential_location("./auth")
    if username == "anonymous":
        client.anonymous_login()
        return
    if username == "" and exists("./auth/lastuser.txt") and relogin:
        with open("./auth/lastuser.txt", "r") as f: username = f.read()
    if username != "":
        keypath = "./auth/" + username + ".txt"
        if exists(keypath):
            with open(keypath, "r") as f: login_key = f.read()
            print("Logging in as", username, "using saved login key")
            result = client.login(username, login_key=login_key)
            while result in (EResult.AccountLoginDeniedNeedTwoFactor, EResult.TwoFactorCodeMismatch):
                result = client.login(username, login_key=login_key, two_factor_code=input("Enter 2FA code: "))
            while result in (EResult.AccountLogonDenied, EResult.InvalidLoginAuthCode):
                result = client.login(username, login_key=login_key, auth_code=input("Enter email code: "))
            if result == EResult.OK: return post_login(client, used_login_key=True)
        client.cli_login(username, password) # fallback to CLI prompts if the above didn't work but we still have a specific username
        return post_login(client)
    # if no username, fall back to either anonymous or CLI login based on fallback_anonymous
    if fallback_anonymous:
        client.anonymous_login()
        return
    else:
        client.cli_login()
        return post_login(client)

def post_login(client, used_login_key=False):
    assert(type(client) == SteamClient)
    makedirs("./auth/", exist_ok=True)
    # if not used_login_key:
    #     if not client.login_key:
    #         print("Waiting for login key...")
    #         client.wait_event(SteamClient.EVENT_NEW_LOGIN_KEY)
    #     print("Writing login key...")
    #     with open("./auth/" + client.username + ".txt", "w") as f:
    #         f.write(client.login_key)
    with open("./auth/lastuser.txt", "w") as f:
        f.write(client.username)

if __name__ == "__main__":
    auto_login(SteamClient(), fallback_anonymous=False, relogin=False)
