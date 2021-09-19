# Diabotical Tracker

This is the source code for the Diabotical Patch Tracker found here: https://github.com/ScheduleTracker/DiaboticalTracker

It's old, ugly code. Written in python2.7 because that's what I wrote the first PoC for parsing Epic's binary manifests and chunks in.
Much of the manifest and API code lives on in my [legendary](https://github.com/derrod/legendary) project which serves as a an open-source alternative to the Epic Games Launcher.

Also not using best practices in any way shape or form. View/Use at your own risk.

## Setup notes

Requires `python2.7` + `python-requests` and a git repo called `DiaboticalTracker` in the working directory as well as about 8 GiB of space for the repo + chunk cache.

You'll need a file called `egs_token.json` with the OAuth information for an Epic account that owns Diabotical.
The easiest way of obtaining such a file would be to use [legendary](https://github.com/derrod/legendary) and copy the `user.json` from `~/.config/legendary` after logging in.

There are many hardcoded paths that will need adjusting, and there might be other requirements I forgot.

The actual deployment ran via a cronjob like so:
```crontab
0 */2 * * * cd /home/ubuntu/dbtracker && bash run.sh &>> update.log
```

## Known bugs/issues

- Files that were removed were not deleted from the repo
- git isn't really meant to track binary data like maps, so the repo is big and slow
- Probably more that I can't remember
