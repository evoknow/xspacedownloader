#!/bin/bash

ps auxww | grep python | egrep -i '(bg_|background_|app)' | awk '{print $2}' | xargs kill -9 
