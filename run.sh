date "+%Y-%m-%d %H:%M"

source venv/bin/activate

if [ -z "$SSH_AUTH_SOCK" ] ; then
  eval `ssh-agent -s`
  ssh-add ~/.ssh/id_rsa_db
fi

python diabotical_tracker.py && cd DiaboticalTracker && git push -f && cd ..

kill $SSH_AGENT_PID
echo
