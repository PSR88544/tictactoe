from oophelpers import *
from flask import Flask, render_template, session, request
from flask_socketio import SocketIO, emit, join_room, disconnect, leave_room


app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(threaded=True, host='0.0.0.0', port=5000)