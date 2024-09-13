from oophelpers import *
from flask import Flask, render_template, session, request
from flask_socketio import SocketIO, emit, join_room, disconnect, leave_room
import pymysql
import boto3

app = Flask(__name__)
app.config['SECRET_KEY'] = 'top-secret!'
app.config['SESSION_TYPE'] = 'filesystem'

socketio = SocketIO(app)

# Database connection
def get_db_connection():
    return pymysql.connect(
        host='your-rds-endpoint',
        user='your-username',
        password='your-password',
        db='your-database',
        cursorclass=pymysql.cursors.DictCursor
    )

@app.route('/')
def index():
    return render_template('index.html')

# ! server-client communication

@socketio.event
def connect():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "INSERT INTO connectedToPortalUsers (sid) VALUES (%s)"
            cursor.execute(sql, (request.sid,))
        connection.commit()
    finally:
        connection.close()
    
    emit('connection-established', 'go', to=request.sid)

@socketio.on('check-game-room')
def checkGameRoom(data):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # Update player info
            sql = "UPDATE connectedToPortalUsers SET name=%s, requestedGameRoom=%s WHERE sid=%s"
            cursor.execute(sql, (data['username'], data['room'], request.sid))
            
            # Check if room exists
            sql = "SELECT * FROM activeGamingRooms WHERE name=%s"
            cursor.execute(sql, (data['room'],))
            room = cursor.fetchone()
            
            if room is None:
                # Create new room
                sql = "INSERT INTO activeGamingRooms (name) VALUES (%s)"
                cursor.execute(sql, (data['room'],))
                room_id = cursor.lastrowid
            else:
                room_id = room['id']
            
            # Add player to room
            sql = "INSERT INTO roomPlayers (room_id, player_sid) VALUES (%s, %s)"
            cursor.execute(sql, (room_id, request.sid))
        connection.commit()
        
        join_room(data['room'])
        emit('tooManyPlayers', 'go', to=request.sid)
    finally:
        connection.close()
    
    session['username'] = data['username']
    session['room'] = data['room']

@socketio.event
def readyToStart():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT player_sid FROM roomPlayers WHERE room_id=(SELECT id FROM activeGamingRooms WHERE name=%s)"
            cursor.execute(sql, (session['room'],))
            players = cursor.fetchall()
            onlineClients = [player['player_sid'] for player in players]
        
        emit('clientId', (request.sid, session.get('room')))
        emit('connected-Players', [onlineClients], to=session['room'])
        emit('status', {'clientsNbs': len(onlineClients), 'clientId': request.sid}, to=session['room'])
    finally:
        connection.close()

@socketio.event
def my_broadcast_event(message):
    emit('player message', {'data': message['data'], 'sender': message['sender']}, to=session['room'])

@socketio.event
def startGame(message):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "UPDATE connectedToPortalUsers SET start_game_intention=1 WHERE sid=%s"
            cursor.execute(sql, (request.sid,))
            
            sql = "SELECT COUNT(*) as count FROM connectedToPortalUsers WHERE requestedGameRoom=%s AND start_game_intention=1"
            cursor.execute(sql, (session['room'],))
            count = cursor.fetchone()['count']
            
            if count >= 2:
                activePlayer = randint(0, count - 1)  # Random active player
                emit('start', {'activePlayer': activePlayer, 'started': True}, to=session['room'])
            else:
                emit('waiting second player start', to=session['room'])
        connection.commit()
    finally:
        connection.close()

@socketio.on('turn')
def turn(data):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "SELECT player_sid FROM roomPlayers WHERE room_id=(SELECT id FROM activeGamingRooms WHERE name=%s)"
            cursor.execute(sql, (session['room'],))
            players = cursor.fetchall()
            activePlayer = players[randint(0, len(players) - 1)]['player_sid']
        
        print('turn by {}: position {}'.format(data['player'], data['pos']))
        emit('turn', {'recentPlayer': data['player'], 'lastPos': data['pos'], 'next': activePlayer}, to=session['room'])
    finally:
        connection.close()

@socketio.on('game_status')
def game_status(msg):
    print(msg['status'])

@socketio.event
def disconnect():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "DELETE FROM connectedToPortalUsers WHERE sid=%s"
            cursor.execute(sql, (request.sid,))
            
            sql = "DELETE FROM roomPlayers WHERE player_sid=%s"
            cursor.execute(sql, (request.sid,))
            
            sql = "SELECT COUNT(*) as count FROM roomPlayers WHERE room_id=(SELECT id FROM activeGamingRooms WHERE name=%s)"
            cursor.execute(sql, (session['room'],))
            count = cursor.fetchone()['count']
            
            if count == 0:
                sql = "DELETE FROM activeGamingRooms WHERE name=%s"
                cursor.execute(sql, (session['room'],))
            else:
                emit('disconnect-status', {'clientsNbs': count, 'clientId': request.sid}, to=session['room'])
        connection.commit()
    finally:
        connection.close()
    print("client with sid: {} disconnected".format(request.sid))

if __name__ == '__main__':
    socketio.run(app,host='0.0.0.0', port=5001, debug=True)
